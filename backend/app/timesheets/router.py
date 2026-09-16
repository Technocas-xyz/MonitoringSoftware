"""Timesheets + corrections + project costing (spec 39/70/76)."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.time_authority import now
from app.models.directory import Employee
from app.models.projects import (
    Project,
    Task,
    TaskTimeEntry,
    Timesheet,
    TimesheetCorrection,
    TimesheetEntry,
)
from app.timesheets.service import generate_timesheet

router = APIRouter(tags=["timesheets"])


# ---- schemas ----
class GenerateRequest(BaseModel):
    employee_id: uuid.UUID
    period_start: date
    period_end: date


class TimesheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    period_start: date
    period_end: date
    status: str


class EntryEdit(BaseModel):
    entry_id: uuid.UUID
    worked_seconds: int | None = None
    overtime_seconds: int | None = None
    reason: str


class CorrectionCreate(BaseModel):
    timesheet_id: uuid.UUID | None = None
    entry_id: uuid.UUID | None = None
    request_type: str
    old_value: dict | None = None
    new_value: dict | None = None
    reason: str


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    request_type: str
    status: str
    reason: str


# ---- timesheet lifecycle ----
@router.post("/timesheets/generate", response_model=TimesheetOut, status_code=201)
async def generate(
    payload: GenerateRequest,
    principal: Principal = Depends(require_permission("timesheet.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    ts = await generate_timesheet(
        session, principal.organization_id, payload.employee_id,
        payload.period_start, payload.period_end,
    )
    await session.commit()
    return TimesheetOut.model_validate(ts)


async def _get_ts(session, ts_id) -> Timesheet:
    ts = (await session.execute(select(Timesheet).where(Timesheet.id == ts_id))).scalar_one_or_none()
    if ts is None:
        raise HTTPException(status_code=404, detail="timesheet not found")
    return ts


@router.post("/timesheets/{ts_id}/submit", response_model=TimesheetOut)
async def submit(
    ts_id: uuid.UUID,
    principal: Principal = Depends(require_permission("timesheet.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    ts = await _get_ts(session, ts_id)
    if ts.status == "locked":
        raise HTTPException(status_code=409, detail="timesheet is locked")
    ts.status = "submitted"
    await audit.record(
        session, action="timesheet.submit", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet", target_id=ts.id,
        new_value={"status": "submitted"},
    )
    await session.commit()
    return TimesheetOut.model_validate(ts)


async def _decide(session, principal, ts_id, status_value, action):
    ts = await _get_ts(session, ts_id)
    if ts.status == "locked":
        raise HTTPException(status_code=409, detail="timesheet is locked")
    old = ts.status
    ts.status = status_value
    if status_value == "approved":
        ts.approved_by = principal.user_id
        ts.approved_at = now()
    await audit.record(
        session, action=action, organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet", target_id=ts.id,
        old_value={"status": old}, new_value={"status": status_value},
    )
    await session.commit()
    return TimesheetOut.model_validate(ts)


@router.post("/timesheets/{ts_id}/approve", response_model=TimesheetOut)
async def approve(
    ts_id: uuid.UUID,
    principal: Principal = Depends(require_permission("timesheet.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide(session, principal, ts_id, "approved", "timesheet.approve")


@router.post("/timesheets/{ts_id}/reject", response_model=TimesheetOut)
async def reject(
    ts_id: uuid.UUID,
    principal: Principal = Depends(require_permission("timesheet.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide(session, principal, ts_id, "rejected", "timesheet.reject")


@router.post("/timesheets/{ts_id}/lock", response_model=TimesheetOut)
async def lock(
    ts_id: uuid.UUID,
    principal: Principal = Depends(require_permission("timesheet.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    ts = await _get_ts(session, ts_id)
    ts.status = "locked"
    await audit.record(
        session, action="timesheet.lock", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet", target_id=ts.id,
        new_value={"status": "locked"},
    )
    await session.commit()
    return TimesheetOut.model_validate(ts)


@router.post("/timesheets/{ts_id}/edit", response_model=TimesheetOut)
async def edit_entry(
    ts_id: uuid.UUID,
    payload: EntryEdit,
    principal: Principal = Depends(require_permission("timesheet.edit")),
    session: AsyncSession = Depends(get_tenant_session),
):
    ts = await _get_ts(session, ts_id)
    if ts.status == "locked":
        raise HTTPException(status_code=409, detail="timesheet is locked")
    entry = (
        await session.execute(select(TimesheetEntry).where(TimesheetEntry.id == payload.entry_id))
    ).scalar_one_or_none()
    if entry is None or entry.timesheet_id != ts.id:
        raise HTTPException(status_code=404, detail="entry not found")

    old = {"worked_seconds": entry.worked_seconds, "overtime_seconds": entry.overtime_seconds}
    if payload.worked_seconds is not None:
        entry.worked_seconds = payload.worked_seconds
    if payload.overtime_seconds is not None:
        entry.overtime_seconds = payload.overtime_seconds
    new = {"worked_seconds": entry.worked_seconds, "overtime_seconds": entry.overtime_seconds}

    # Every manual edit is audited with a reason (spec 39).
    await audit.record(
        session, action="timesheet.edit", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet_entry", target_id=entry.id,
        old_value=old, new_value=new, reason=payload.reason,
    )
    await session.commit()
    return TimesheetOut.model_validate(ts)


# ---- corrections ----
@router.post("/corrections", response_model=CorrectionOut, status_code=201)
async def create_correction(
    payload: CorrectionCreate,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    c = TimesheetCorrection(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        timesheet_id=payload.timesheet_id, entry_id=payload.entry_id,
        request_type=payload.request_type, old_value=payload.old_value,
        new_value=payload.new_value, reason=payload.reason,
        status="pending", requested_by=principal.user_id, created_at=now(),
    )
    session.add(c)
    await audit.record(
        session, action="correction.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet_correction", target_id=c.id,
        new_value={"request_type": c.request_type},
    )
    await session.commit()
    return CorrectionOut.model_validate(c)


async def _decide_correction(session, principal, correction_id, status_value):
    c = (
        await session.execute(select(TimesheetCorrection).where(TimesheetCorrection.id == correction_id))
    ).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="correction not found")
    c.status = status_value
    c.approver_user_id = principal.user_id
    c.decided_at = now()
    await audit.record(
        session, action=f"correction.{status_value}", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="timesheet_correction", target_id=c.id,
        old_value=c.old_value, new_value=c.new_value, reason=c.reason,
    )
    await session.commit()
    return CorrectionOut.model_validate(c)


@router.post("/corrections/{correction_id}/approve", response_model=CorrectionOut)
async def approve_correction(
    correction_id: uuid.UUID,
    principal: Principal = Depends(require_permission("correction.review")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide_correction(session, principal, correction_id, "approved")


@router.post("/corrections/{correction_id}/reject", response_model=CorrectionOut)
async def reject_correction(
    correction_id: uuid.UUID,
    principal: Principal = Depends(require_permission("correction.review")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _decide_correction(session, principal, correction_id, "rejected")


# ---- project costing (rate-gated, spec 76) ----
class CostingOut(BaseModel):
    project_id: uuid.UUID
    total_seconds: int
    total_cost: float
    currency: str = "USD"


@router.get("/projects/{project_id}/costing", response_model=CostingOut)
async def project_costing(
    project_id: uuid.UUID,
    principal: Principal = Depends(require_permission("rate.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    proj = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")

    # Sum task time entries for tasks in this project, priced by each employee's hourly rate.
    task_ids = [
        t.id for t in (
            await session.execute(select(Task).where(Task.project_id == project_id))
        ).scalars().all()
    ]
    total_seconds = 0
    total_cost = 0.0
    if task_ids:
        entries = (
            await session.execute(
                select(TaskTimeEntry).where(
                    TaskTimeEntry.task_id.in_(task_ids),
                    TaskTimeEntry.duration_seconds.is_not(None),
                )
            )
        ).scalars().all()
        # cache employee rate
        rates: dict[uuid.UUID, float] = {}
        for e in entries:
            total_seconds += e.duration_seconds or 0
            if e.employee_id not in rates:
                emp = (
                    await session.execute(select(Employee).where(Employee.id == e.employee_id))
                ).scalar_one_or_none()
                rates[e.employee_id] = float(emp.hourly_rate) if emp and emp.hourly_rate else 0.0
            total_cost += (e.duration_seconds or 0) / 3600.0 * rates[e.employee_id]

    return CostingOut(
        project_id=project_id, total_seconds=total_seconds, total_cost=round(total_cost, 2)
    )
