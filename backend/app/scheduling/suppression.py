"""Determine whether a given date is a non-working day for an employee due to approved leave
or an organization holiday. Used by the auto scheduler to cancel (not miss) shifts."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduling import HolidayDay, LeaveRequest


async def on_approved_leave(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, day: date
) -> bool:
    row = (
        await session.execute(
            select(LeaveRequest).where(
                LeaveRequest.organization_id == org_id,
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= day,
                LeaveRequest.end_date >= day,
            )
        )
    ).scalars().first()
    return row is not None


async def is_holiday(session: AsyncSession, org_id: uuid.UUID, day: date) -> bool:
    row = (
        await session.execute(
            select(HolidayDay).where(
                HolidayDay.organization_id == org_id, HolidayDay.day == day
            )
        )
    ).scalars().first()
    return row is not None


async def is_suppressed(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, day: date
) -> bool:
    return await on_approved_leave(session, org_id, employee_id, day) or await is_holiday(
        session, org_id, day
    )
