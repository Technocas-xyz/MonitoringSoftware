"""Timesheet generation from attendance (spec 39).

A timesheet for a period is built from the employee's derived attendance rows in that period.
Timesheets are never the source of truth; they project authoritative attendance for approval.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shifts import Attendance
from app.models.projects import Timesheet, TimesheetEntry


async def generate_timesheet(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID,
    period_start: date, period_end: date,
) -> Timesheet:
    ts = (
        await session.execute(
            select(Timesheet).where(
                Timesheet.organization_id == org_id,
                Timesheet.employee_id == employee_id,
                Timesheet.period_start == period_start,
                Timesheet.period_end == period_end,
            )
        )
    ).scalar_one_or_none()
    if ts is None:
        ts = Timesheet(
            id=uuid.uuid4(), organization_id=org_id, employee_id=employee_id,
            period_start=period_start, period_end=period_end, status="draft",
        )
        session.add(ts)
        await session.flush()

    # Locked timesheets are immutable — never regenerate entries.
    if ts.status == "locked":
        return ts

    # Rebuild entries from attendance in the period.
    existing = (
        await session.execute(
            select(TimesheetEntry).where(TimesheetEntry.timesheet_id == ts.id)
        )
    ).scalars().all()
    for e in existing:
        await session.delete(e)
    await session.flush()

    attendance = (
        await session.execute(
            select(Attendance).where(
                Attendance.organization_id == org_id,
                Attendance.employee_id == employee_id,
                Attendance.work_date >= period_start,
                Attendance.work_date <= period_end,
            )
        )
    ).scalars().all()

    for att in attendance:
        scheduled = 0
        if att.scheduled_start and att.scheduled_end:
            scheduled = int((att.scheduled_end - att.scheduled_start).total_seconds())
        session.add(TimesheetEntry(
            id=uuid.uuid4(), organization_id=org_id, timesheet_id=ts.id,
            work_date=att.work_date, scheduled_seconds=max(0, scheduled),
            worked_seconds=att.worked_seconds, break_seconds=att.break_seconds,
            overtime_seconds=att.overtime_seconds, status=att.status,
        ))
    await session.flush()
    return ts
