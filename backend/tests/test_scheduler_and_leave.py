"""Auto scheduler (auto-start/end, missed) and leave/holiday suppression."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.scheduling import HolidayCalendar, HolidayDay, LeaveRequest
from app.models.shifts import (
    AUTO_COMPLETED,
    AVAILABLE,
    CANCELLED,
    MISSED,
    WORKING,
    Shift,
)
from app.shifts import scheduler
from tests.factories import make_org_and_employee


def _policy(**o):
    base = {
        "auto_start": False, "auto_end": True, "late_threshold_min": 15,
        "latest_clock_in_min": 30, "allow_overtime": True, "allow_early_clockout": True,
        "allow_break": True, "allow_multiple_breaks": True,
    }
    base.update(o)
    return base


async def _mk_shift(org_id, emp_id, start_off, end_off, policy, state=AVAILABLE):
    async with get_sessionmaker()() as s:
        n = now()
        sh = Shift(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, state=state,
            scheduled_start=n + timedelta(minutes=start_off),
            scheduled_end=n + timedelta(minutes=end_off),
            timezone="UTC", policy_snapshot=policy, version=0,
        )
        s.add(sh)
        await s.commit()
        return sh.id


@pytest.mark.asyncio
async def test_auto_start_triggers_when_due(session_factory):
    org_id, emp_id = await make_org_and_employee()
    sid = await _mk_shift(org_id, emp_id, start_off=-1, end_off=480, policy=_policy(auto_start=True))
    async with get_sessionmaker()() as s:
        n = await scheduler.run_auto_start(s, org_id)
        await s.commit()
        assert n == 1
        sh = (await s.execute(select(Shift).where(Shift.id == sid))).scalar_one()
        assert sh.state == WORKING


@pytest.mark.asyncio
async def test_auto_start_skipped_when_not_configured(session_factory):
    org_id, emp_id = await make_org_and_employee()
    await _mk_shift(org_id, emp_id, start_off=-1, end_off=480, policy=_policy(auto_start=False))
    async with get_sessionmaker()() as s:
        n = await scheduler.run_auto_start(s, org_id)
        await s.commit()
        assert n == 0


@pytest.mark.asyncio
async def test_auto_end_triggers_when_past_scheduled_end(session_factory):
    org_id, emp_id = await make_org_and_employee()
    sid = await _mk_shift(
        org_id, emp_id, start_off=-120, end_off=-1, policy=_policy(auto_end=True), state=WORKING
    )
    async with get_sessionmaker()() as s:
        n = await scheduler.run_auto_end(s, org_id)
        await s.commit()
        assert n == 1
        sh = (await s.execute(select(Shift).where(Shift.id == sid))).scalar_one()
        assert sh.state == AUTO_COMPLETED


@pytest.mark.asyncio
async def test_mark_missed_past_window(session_factory):
    org_id, emp_id = await make_org_and_employee()
    # scheduled start 2h ago, latest clock-in 30m -> deadline passed, never started
    sid = await _mk_shift(org_id, emp_id, start_off=-120, end_off=360, policy=_policy())
    async with get_sessionmaker()() as s:
        n = await scheduler.mark_missed(s, org_id)
        await s.commit()
        assert n == 1
        sh = (await s.execute(select(Shift).where(Shift.id == sid))).scalar_one()
        assert sh.state == MISSED


@pytest.mark.asyncio
async def test_missed_becomes_cancelled_on_approved_leave(session_factory):
    org_id, emp_id = await make_org_and_employee()
    sid = await _mk_shift(org_id, emp_id, start_off=-120, end_off=360, policy=_policy())
    async with get_sessionmaker()() as s:
        work_date = now().date()
        s.add(LeaveRequest(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, type="annual",
            start_date=work_date, end_date=work_date, status="approved",
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        await scheduler.mark_missed(s, org_id)
        await s.commit()
        sh = (await s.execute(select(Shift).where(Shift.id == sid))).scalar_one()
        assert sh.state == CANCELLED  # suppressed by leave, not MISSED


@pytest.mark.asyncio
async def test_holiday_suppresses_missed(session_factory):
    org_id, emp_id = await make_org_and_employee()
    sid = await _mk_shift(org_id, emp_id, start_off=-120, end_off=360, policy=_policy())
    async with get_sessionmaker()() as s:
        cal = HolidayCalendar(id=uuid.uuid4(), organization_id=org_id, name="Nat")
        s.add(cal)
        await s.flush()
        s.add(HolidayDay(
            id=uuid.uuid4(), organization_id=org_id, calendar_id=cal.id,
            day=now().date(), name="Holiday",
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        await scheduler.mark_missed(s, org_id)
        await s.commit()
        sh = (await s.execute(select(Shift).where(Shift.id == sid))).scalar_one()
        assert sh.state == CANCELLED
