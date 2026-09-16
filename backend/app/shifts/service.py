"""Shift orchestration: creation with policy snapshot, and transition wrappers that also
recompute attendance. Sits between the router/scheduler and the pure state_machine."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directory import Employee
from app.models.shifts import (
    ACTIVE_STATES,
    AVAILABLE,
    SCHEDULED,
    TERMINAL_STATES,
    Shift,
)
from app.policy.resolver import resolve_for_employee
from app.scheduling.resolver import occurrences_for
from app.shifts import attendance as attendance_engine
from app.shifts import errors, state_machine


async def _has_active_shift(session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID) -> bool:
    row = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id,
                Shift.employee_id == employee_id,
                Shift.state.in_(ACTIVE_STATES),
            )
        )
    ).scalars().first()
    return row is not None


async def create_shift_for_day(
    session: AsyncSession,
    employee: Employee,
    day: date,
    *,
    initial_state: str = AVAILABLE,
) -> Shift:
    """Create a shift for an employee's schedule occurrence on a day, freezing policy.

    Uses the first occurrence of the day. If no schedule occurrence exists, creates a shift
    with no scheduled window (flexible/ad-hoc start).
    """
    if await _has_active_shift(session, employee.organization_id, employee.id):
        raise errors.AlreadyActive("employee already has an active shift")

    schedule, occs, tz = await occurrences_for(session, employee, day)
    resolved = await resolve_for_employee(session, employee)
    snapshot = {**resolved.shift, "monitoring": resolved.monitoring}

    scheduled_start = occs[0].scheduled_start if occs else None
    scheduled_end = occs[0].scheduled_end if occs else None
    effective_tz = tz or employee.timezone or "UTC"

    shift = Shift(
        id=uuid.uuid4(),
        organization_id=employee.organization_id,
        employee_id=employee.id,
        schedule_id=schedule.id if schedule else None,
        state=initial_state,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        timezone=effective_tz,
        policy_snapshot=snapshot,
        schedule_snapshot=(
            {"type": schedule.type, "definition": schedule.definition} if schedule else None
        ),
        version=0,
    )
    session.add(shift)
    await session.flush()
    return shift


async def get_shift(session: AsyncSession, shift_id: uuid.UUID) -> Shift:
    shift = (
        await session.execute(select(Shift).where(Shift.id == shift_id))
    ).scalar_one_or_none()
    if shift is None:
        raise errors.NotFound("shift not found")
    return shift


async def _emit(session: AsyncSession, shift: Shift, event: str) -> None:
    """Fire a webhook event for a shift transition (spec 78). Best-effort; never blocks."""
    from app.webhooks.service import emit

    await emit(
        session, shift.organization_id, event,
        {"shift_id": str(shift.id), "employee_id": str(shift.employee_id), "state": shift.state},
    )


# --- transition wrappers that refresh attendance + emit webhook events after each change ---
async def start(session: AsyncSession, shift: Shift, **kw) -> Shift:
    shift = await state_machine.start(session, shift, **kw)
    await attendance_engine.derive_for_shift(session, shift)
    await _emit(session, shift, "shift.started")
    return shift


async def pause(session: AsyncSession, shift: Shift, **kw) -> Shift:
    shift = await state_machine.pause(session, shift, **kw)
    await attendance_engine.derive_for_shift(session, shift)
    await _emit(session, shift, "shift.paused")
    return shift


async def resume(session: AsyncSession, shift: Shift, **kw) -> Shift:
    shift = await state_machine.resume(session, shift, **kw)
    await attendance_engine.derive_for_shift(session, shift)
    await _emit(session, shift, "shift.resumed")
    return shift


async def end(session: AsyncSession, shift: Shift, **kw) -> Shift:
    shift = await state_machine.end(session, shift, **kw)
    await attendance_engine.derive_for_shift(session, shift)
    await _emit(session, shift, "shift.ended")
    return shift
