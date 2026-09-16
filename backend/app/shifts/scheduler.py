"""Auto shift lifecycle driver (spec 14, docs/04).

These are the server-authoritative scheduled operations, run periodically by Celery beat in
production. They are plain async functions so they can be unit-tested directly and invoked by
the worker layer (app/worker/tasks.py).

Operations, all using server time:
  - ensure_daily_shifts:  create AVAILABLE/SCHEDULED shifts for employees with an occurrence
                          today (skipping suppressed days -> CANCELLED not created).
  - run_auto_start:       AVAILABLE shifts whose policy.auto_start and time >= scheduled_start
                          -> AUTO_START -> WORKING.
  - run_auto_end:         active shifts whose policy.auto_end and time >= scheduled_end
                          -> AUTO_END -> AUTO_COMPLETED.
  - mark_missed:          AVAILABLE/SCHEDULED shifts past the latest clock-in window with no
                          start -> MISSED (unless suppressed -> CANCELLED).

Every operation writes shift_events + audit and re-derives attendance.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.time_authority import now, to_utc
from app.models.directory import Employee
from app.models.shifts import (
    AVAILABLE,
    CANCELLED,
    MISSED,
    SCHEDULED,
    WORKING,
    ON_BREAK,
    PAUSED,
    Shift,
)
from app.scheduling import suppression
from app.shifts import attendance as attendance_engine
from app.shifts import service, state_machine


async def ensure_daily_shifts(session: AsyncSession, org_id: uuid.UUID, day: date) -> int:
    """Create today's shifts for employees who have a schedule occurrence and no shift yet."""
    employees = (
        await session.execute(
            select(Employee).where(
                Employee.organization_id == org_id, Employee.status == "active"
            )
        )
    ).scalars().all()

    created = 0
    for emp in employees:
        # Skip if suppressed (leave/holiday) -> no shift, treated as rest day.
        if await suppression.is_suppressed(session, org_id, emp.id, day):
            continue
        # Skip if a shift already exists for the day.
        existing = (
            await session.execute(
                select(Shift).where(
                    Shift.organization_id == org_id,
                    Shift.employee_id == emp.id,
                )
            )
        ).scalars().all()
        if any(
            s.scheduled_start and to_utc(s.scheduled_start).date() == day for s in existing
        ):
            continue
        try:
            shift = await service.create_shift_for_day(session, emp, day)
        except Exception:
            continue
        if shift.scheduled_start is None:
            # No occurrence today: drop the ad-hoc shift (nothing scheduled).
            await session.delete(shift)
            continue
        created += 1
    await session.flush()
    return created


async def run_auto_start(session: AsyncSession, org_id: uuid.UUID) -> int:
    server_now = now()
    shifts = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id, Shift.state == AVAILABLE
            )
        )
    ).scalars().all()
    started = 0
    for shift in shifts:
        policy = shift.policy_snapshot or {}
        if not policy.get("auto_start"):
            continue
        if shift.scheduled_start and server_now >= to_utc(shift.scheduled_start):
            await state_machine.start(session, shift, auto=True)
            await attendance_engine.derive_for_shift(session, shift)
            started += 1
    await session.flush()
    return started


async def run_auto_end(session: AsyncSession, org_id: uuid.UUID) -> int:
    server_now = now()
    shifts = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id,
                Shift.state.in_((WORKING, ON_BREAK, PAUSED)),
            )
        )
    ).scalars().all()
    ended = 0
    for shift in shifts:
        policy = shift.policy_snapshot or {}
        if not policy.get("auto_end"):
            continue
        if shift.scheduled_end and server_now >= to_utc(shift.scheduled_end):
            await state_machine.end(session, shift, auto=True)
            await attendance_engine.derive_for_shift(session, shift)
            ended += 1
    await session.flush()
    return ended


async def detect_monitoring_lost(session: AsyncSession, org_id: uuid.UUID, silence_seconds: int = 300) -> int:
    """Flag active shifts whose monitoring is required but whose device has gone silent.

    A device is "silent" if its last_seen_at is older than silence_seconds (heartbeat gap).
    Writes an audit record per occurrence; the full alert engine (Phase 7) turns these into
    alerts/notifications. Returns the number flagged.
    """
    from datetime import timedelta

    from app.models.devices import Device

    server_now = now()
    threshold = server_now - timedelta(seconds=silence_seconds)

    shifts = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id,
                Shift.state.in_((WORKING, ON_BREAK, PAUSED)),
            )
        )
    ).scalars().all()

    flagged = 0
    for shift in shifts:
        policy = shift.policy_snapshot or {}
        if not policy.get("monitoring_required", False):
            continue
        # Any approved device for this employee seen recently?
        devices = (
            await session.execute(
                select(Device).where(
                    Device.organization_id == org_id,
                    Device.employee_id == shift.employee_id,
                    Device.status == "approved",
                )
            )
        ).scalars().all()
        recent = any(d.last_seen_at and to_utc(d.last_seen_at) >= threshold for d in devices)
        if recent:
            continue
        await audit.record(
            session, action="monitoring.lost", organization_id=org_id,
            target_type="shift", target_id=shift.id,
            new_value={"state": shift.state, "reason": "agent heartbeat gap"},
        )
        flagged += 1
    await session.flush()
    return flagged


async def mark_missed(session: AsyncSession, org_id: uuid.UUID) -> int:
    server_now = now()
    shifts = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id,
                Shift.state.in_((AVAILABLE, SCHEDULED)),
            )
        )
    ).scalars().all()
    marked = 0
    for shift in shifts:
        if shift.scheduled_start is None:
            continue
        policy = shift.policy_snapshot or {}
        latest_min = policy.get("latest_clock_in_min") or 0
        deadline = to_utc(shift.scheduled_start) + timedelta(minutes=latest_min)
        if server_now <= deadline:
            continue

        work_date = to_utc(shift.scheduled_start).date()
        suppressed = await suppression.is_suppressed(
            session, org_id, shift.employee_id, work_date
        )
        new_state = CANCELLED if suppressed else MISSED
        old = shift.state
        shift.state = new_state
        shift.version = (shift.version or 0) + 1
        await audit.record(
            session,
            action="shift.cancelled" if suppressed else "shift.missed",
            organization_id=org_id, target_type="shift", target_id=shift.id,
            old_value={"state": old}, new_value={"state": new_state},
        )
        await attendance_engine.derive_for_shift(session, shift)
        marked += 1
    await session.flush()
    return marked
