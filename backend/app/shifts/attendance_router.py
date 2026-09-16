"""Attendance read API (spec 8/37)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.shifts import Attendance

router = APIRouter(prefix="/attendance", tags=["attendance"])


class AttendanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    shift_id: uuid.UUID | None
    work_date: date
    status: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    worked_seconds: int
    break_seconds: int
    idle_seconds: int
    late_seconds: int
    early_leave_seconds: int
    overtime_seconds: int


@router.get("", response_model=list[AttendanceOut])
async def list_attendance(
    employee_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    status: str | None = None,
    principal: Principal = Depends(require_permission("attendance.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = select(Attendance)
    if employee_id:
        stmt = stmt.where(Attendance.employee_id == employee_id)
    if from_date:
        stmt = stmt.where(Attendance.work_date >= from_date)
    if to_date:
        stmt = stmt.where(Attendance.work_date <= to_date)
    if status:
        stmt = stmt.where(Attendance.status == status)
    stmt = stmt.order_by(Attendance.work_date.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()
    return [AttendanceOut.model_validate(r) for r in rows]
