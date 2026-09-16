"""Schedules API: CRUD, assignment, and occurrence preview."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.directory import Employee
from app.models.scheduling import ScheduleAssignment, WorkSchedule
from app.scheduling.resolver import occurrences_for
from app.scheduling.schemas import (
    OccurrenceOut,
    OccurrencesResponse,
    ScheduleAssignRequest,
    WorkScheduleCreate,
    WorkScheduleOut,
)

router = APIRouter(tags=["schedules"])

_VALID_TYPES = {"fixed", "flexible", "rotating", "custom"}


@router.post("/schedules", response_model=WorkScheduleOut, status_code=201)
async def create_schedule(
    payload: WorkScheduleCreate,
    principal: Principal = Depends(require_permission("schedule.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if payload.type not in _VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {_VALID_TYPES}")
    sched = WorkSchedule(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        name=payload.name,
        type=payload.type,
        timezone=payload.timezone,
        definition=payload.definition,
    )
    session.add(sched)
    await audit.record(
        session, action="schedule.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="work_schedule", target_id=sched.id,
        new_value={"name": sched.name, "type": sched.type},
    )
    await session.commit()
    return WorkScheduleOut.model_validate(sched)


@router.get("/schedules", response_model=list[WorkScheduleOut])
async def list_schedules(
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(WorkSchedule))).scalars().all()
    return [WorkScheduleOut.model_validate(s) for s in rows]


@router.post("/schedules/{schedule_id}/assign", status_code=201)
async def assign_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleAssignRequest,
    principal: Principal = Depends(require_permission("schedule.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    sched = (
        await session.execute(select(WorkSchedule).where(WorkSchedule.id == schedule_id))
    ).scalar_one_or_none()
    if sched is None:
        raise HTTPException(status_code=404, detail="schedule not found")

    assignment = ScheduleAssignment(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        schedule_id=schedule_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        priority=payload.priority,
    )
    session.add(assignment)
    await audit.record(
        session, action="schedule.assign", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="schedule_assignment", target_id=assignment.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return {"id": str(assignment.id)}


@router.get("/schedules/occurrences", response_model=OccurrencesResponse)
async def get_occurrences(
    employee_id: uuid.UUID,
    day: date,
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="employee not found")

    schedule, occs, tz = await occurrences_for(session, emp, day)
    return OccurrencesResponse(
        employee_id=employee_id,
        day=day,
        schedule_id=schedule.id if schedule else None,
        timezone=tz,
        occurrences=[
            OccurrenceOut(scheduled_start=o.scheduled_start, scheduled_end=o.scheduled_end)
            for o in occs
        ],
    )
