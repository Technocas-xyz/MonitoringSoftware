"""Shift state machine transitions, guards, and attendance derivation."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.shifts import (
    AVAILABLE,
    COMPLETED,
    ON_BREAK,
    WORKING,
    Shift,
)
from app.shifts import errors, service, state_machine
from app.shifts.attendance import LATE, PRESENT
from tests.factories import make_org_and_employee


def _policy(**overrides) -> dict:
    base = {
        "tracking_mode": "hybrid",
        "earliest_clock_in_min": 15,
        "latest_clock_in_min": 30,
        "late_threshold_min": 15,
        "allow_break": True,
        "max_break_seconds": 3600,
        "allow_multiple_breaks": True,
        "allow_early_clockout": False,
        "allow_overtime": True,
        "overtime_requires_approval": True,
        "auto_start": False,
        "auto_end": True,
        "monitoring_required": True,
    }
    base.update(overrides)
    return base


async def _make_shift(org_id, emp_id, *, sched_start_offset_min, sched_end_offset_min, policy=None):
    async with get_sessionmaker()() as s:
        n = now()
        shift = Shift(
            id=uuid.uuid4(),
            organization_id=org_id,
            employee_id=emp_id,
            state=AVAILABLE,
            scheduled_start=n + timedelta(minutes=sched_start_offset_min),
            scheduled_end=n + timedelta(minutes=sched_end_offset_min),
            timezone="UTC",
            policy_snapshot=policy or _policy(),
            version=0,
        )
        s.add(shift)
        await s.commit()
        return shift.id


async def _load(s, shift_id) -> Shift:
    from sqlalchemy import select

    return (await s.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()


@pytest.mark.asyncio
async def test_start_within_window(session_factory):
    org_id, emp_id = await make_org_and_employee()
    # scheduled to start now; well within window
    shift_id = await _make_shift(org_id, emp_id, sched_start_offset_min=0, sched_end_offset_min=480)
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        await service.start(s, shift)
        await s.commit()
        assert shift.state == WORKING
        assert shift.actual_start is not None


@pytest.mark.asyncio
async def test_start_before_window_rejected(session_factory):
    org_id, emp_id = await make_org_and_employee()
    # starts in 2 hours; earliest clock-in only 15 min before -> too early
    shift_id = await _make_shift(org_id, emp_id, sched_start_offset_min=120, sched_end_offset_min=600)
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        with pytest.raises(errors.WindowNotOpen):
            await service.start(s, shift)


@pytest.mark.asyncio
async def test_duplicate_start_is_idempotent(session_factory):
    org_id, emp_id = await make_org_and_employee()
    shift_id = await _make_shift(org_id, emp_id, sched_start_offset_min=0, sched_end_offset_min=480)
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        await service.start(s, shift, event_id="evt-start-1")
        await s.commit()
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        # Same event_id -> no-op, stays WORKING (no error, no second start event)
        await service.start(s, shift, event_id="evt-start-1")
        await s.commit()
        assert shift.state == WORKING


@pytest.mark.asyncio
async def test_pause_resume_end_flow(session_factory):
    org_id, emp_id = await make_org_and_employee()
    shift_id = await _make_shift(
        org_id, emp_id, sched_start_offset_min=0, sched_end_offset_min=-1,
        policy=_policy(allow_early_clockout=True),
    )
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        await service.start(s, shift)
        await service.pause(s, shift, is_break=True)
        assert shift.state == ON_BREAK
        await service.resume(s, shift)
        assert shift.state == WORKING
        await service.end(s, shift)
        assert shift.state == COMPLETED
        await s.commit()


@pytest.mark.asyncio
async def test_early_clockout_blocked_by_policy(session_factory):
    org_id, emp_id = await make_org_and_employee()
    # scheduled end far in the future; early clock-out disallowed
    shift_id = await _make_shift(
        org_id, emp_id, sched_start_offset_min=0, sched_end_offset_min=480,
        policy=_policy(allow_early_clockout=False),
    )
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        await service.start(s, shift)
        with pytest.raises(errors.NotPermitted):
            await service.end(s, shift)


@pytest.mark.asyncio
async def test_resume_from_working_rejected(session_factory):
    org_id, emp_id = await make_org_and_employee()
    shift_id = await _make_shift(org_id, emp_id, sched_start_offset_min=0, sched_end_offset_min=480)
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        await service.start(s, shift)
        with pytest.raises(errors.InvalidTransition):
            await service.resume(s, shift)


@pytest.mark.asyncio
async def test_late_attendance_status(session_factory):
    org_id, emp_id = await make_org_and_employee()
    # scheduled to have started 30 min ago; late_threshold 15 -> LATE
    shift_id = await _make_shift(
        org_id, emp_id, sched_start_offset_min=-30, sched_end_offset_min=450,
        policy=_policy(late_threshold_min=15),
    )
    async with get_sessionmaker()() as s:
        shift = await _load(s, shift_id)
        att = None
        await service.start(s, shift)
        from app.shifts.attendance import derive_for_shift

        att = await derive_for_shift(s, shift)
        await s.commit()
        assert att.late_seconds > 0
        assert att.status in (LATE, PRESENT)  # PARTIAL not expected since started
        assert att.status == LATE
