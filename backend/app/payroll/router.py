"""Payroll API (spec 77). Restricted to payroll.run; payroll data is salary-sensitive."""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.payroll import PayrollLine, PayrollRun
from app.payroll.service import generate_run

router = APIRouter(prefix="/payroll", tags=["payroll"])


class RunRequest(BaseModel):
    period_start: date
    period_end: date


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    period_start: date
    period_end: date
    status: str


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    line_type: str
    hours: float
    rate: float
    amount: float


@router.post("/runs", response_model=RunOut, status_code=201)
async def create_run(
    payload: RunRequest,
    principal: Principal = Depends(require_permission("payroll.run")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if payload.period_end < payload.period_start:
        raise HTTPException(status_code=422, detail="period_end before period_start")
    run = await generate_run(
        session, principal.organization_id, payload.period_start, payload.period_end
    )
    await audit.record(
        session, action="payroll.run", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="payroll_run", target_id=run.id,
        new_value={"period_start": payload.period_start.isoformat(),
                   "period_end": payload.period_end.isoformat()},
    )
    await session.commit()
    return RunOut.model_validate(run)


@router.get("/runs/{run_id}/lines", response_model=list[LineOut])
async def run_lines(
    run_id: uuid.UUID,
    principal: Principal = Depends(require_permission("payroll.run")),
    session: AsyncSession = Depends(get_tenant_session),
):
    run = (await session.execute(select(PayrollRun).where(PayrollRun.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="payroll run not found")
    rows = (
        await session.execute(select(PayrollLine).where(PayrollLine.run_id == run_id))
    ).scalars().all()
    return [LineOut.model_validate(line) for line in rows]
