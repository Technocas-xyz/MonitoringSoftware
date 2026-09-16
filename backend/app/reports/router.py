"""Reports API (spec 37/38/65): synchronous generate + download, and report schedules."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.alerts import ReportSchedule
from app.reports import builders, exporters

router = APIRouter(tags=["reports"])


class ReportRequest(BaseModel):
    report_type: str
    format: str = "csv"  # csv|xlsx|pdf
    from_date: date
    to_date: date
    employee_id: uuid.UUID | None = None


@router.post("/reports/generate")
async def generate_report(
    payload: ReportRequest,
    principal: Principal = Depends(require_permission("report.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        data = await builders.build(
            session, payload.report_type, principal.organization_id,
            payload.from_date, payload.to_date, payload.employee_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    content, content_type, ext = exporters.export(data, payload.format)
    await audit.record(
        session, action="report.generate", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="report",
        new_value={"type": payload.report_type, "format": ext,
                   "from": payload.from_date.isoformat(), "to": payload.to_date.isoformat()},
    )
    await session.commit()
    filename = f"{payload.report_type}_{payload.from_date}_{payload.to_date}.{ext}"
    return Response(
        content=content, media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class ScheduleCreate(BaseModel):
    report_type: str
    cron: str
    format: str = "pdf"
    filters: dict = Field(default_factory=dict)
    recipients: list[str] = Field(default_factory=list)


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    report_type: str
    cron: str
    format: str
    enabled: bool


@router.post("/report-schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    payload: ScheduleCreate,
    principal: Principal = Depends(require_permission("report.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    sched = ReportSchedule(
        id=uuid.uuid4(), organization_id=principal.organization_id, **payload.model_dump()
    )
    session.add(sched)
    await audit.record(
        session, action="report.schedule.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="report_schedule", target_id=sched.id,
        new_value={"report_type": sched.report_type, "cron": sched.cron},
    )
    await session.commit()
    return ScheduleOut.model_validate(sched)


@router.get("/report-schedules", response_model=list[ScheduleOut])
async def list_schedules(
    principal: Principal = Depends(require_permission("report.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(ReportSchedule))).scalars().all()
    return [ScheduleOut.model_validate(r) for r in rows]
