"""Leave and holiday API (spec 40, 71).

Approved leave and holidays suppress attendance violations: the auto scheduler cancels the
day's shift (REST_DAY) instead of marking it MISSED. See app/shifts/scheduler.py.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.time_authority import now
from app.models.scheduling import HolidayCalendar, HolidayDay, LeaveRequest

router = APIRouter(tags=["leave"])


# ---- Leave ----
class LeaveCreate(BaseModel):
    employee_id: uuid.UUID
    type: str
    start_date: date
    end_date: date
    reason: str | None = None


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    type: str
    start_date: date
    end_date: date
    status: str


@router.post("/leave", response_model=LeaveOut, status_code=201)
async def create_leave(
    payload: LeaveCreate,
    principal: Principal = Depends(require_permission("leave.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date before start_date")
    lr = LeaveRequest(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        employee_id=payload.employee_id,
        type=payload.type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status="pending",
    )
    session.add(lr)
    await audit.record(
        session, action="leave.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="leave_request", target_id=lr.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return LeaveOut.model_validate(lr)


async def _decide_leave(session, principal, leave_id, status_value):
    lr = (
        await session.execute(select(LeaveRequest).where(LeaveRequest.id == leave_id))
    ).scalar_one_or_none()
    if lr is None:
        raise HTTPException(status_code=404, detail="leave not found")
    lr.status = status_value
    lr.approver_user_id = principal.user_id
    await audit.record(
        session, action=f"leave.{status_value}", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="leave_request", target_id=lr.id,
        new_value={"status": status_value},
    )
    await session.commit()
    return LeaveOut.model_validate(lr)


@router.post("/leave/{leave_id}/approve", response_model=LeaveOut)
async def approve_leave(
    leave_id: uuid.UUID,
    principal: Principal = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide_leave(session, principal, leave_id, "approved")


@router.post("/leave/{leave_id}/reject", response_model=LeaveOut)
async def reject_leave(
    leave_id: uuid.UUID,
    principal: Principal = Depends(require_permission("leave.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide_leave(session, principal, leave_id, "rejected")


@router.get("/leave", response_model=list[LeaveOut])
async def list_leave(
    principal: Principal = Depends(require_permission("leave.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(LeaveRequest))).scalars().all()
    return [LeaveOut.model_validate(r) for r in rows]


# ---- Holidays ----
class HolidayCalendarCreate(BaseModel):
    name: str
    country: str | None = None
    region: str | None = None


class HolidayDayCreate(BaseModel):
    calendar_id: uuid.UUID
    day: date
    name: str


class HolidayCalendarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


@router.post("/holidays/calendars", response_model=HolidayCalendarOut, status_code=201)
async def create_calendar(
    payload: HolidayCalendarCreate,
    principal: Principal = Depends(require_permission("holiday.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    cal = HolidayCalendar(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        name=payload.name, country=payload.country, region=payload.region,
    )
    session.add(cal)
    await audit.record(
        session, action="holiday.calendar.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="holiday_calendar", target_id=cal.id,
        new_value={"name": cal.name},
    )
    await session.commit()
    return HolidayCalendarOut.model_validate(cal)


@router.post("/holidays/days", status_code=201)
async def add_holiday(
    payload: HolidayDayCreate,
    principal: Principal = Depends(require_permission("holiday.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    hd = HolidayDay(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        calendar_id=payload.calendar_id, day=payload.day, name=payload.name,
    )
    session.add(hd)
    await audit.record(
        session, action="holiday.day.add", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="holiday_day", target_id=hd.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return {"id": str(hd.id)}
