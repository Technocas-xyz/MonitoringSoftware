"""AI API (spec 47/89/90). All endpoints require ai.use and run inside the caller's scope.

Each request records an AIJob with a snapshot of the caller's scope for auditability. Scope
is verified BEFORE any data is gathered; out-of-scope targets return 403.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import nl
from app.ai import service as ai_service
from app.ai.scope import ScopeDenied, require_employee_in_scope, require_team_in_scope, scope_snapshot
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.core.time_authority import now
from app.models.ai import AIJob

router = APIRouter(prefix="/ai", tags=["ai"])


class SummaryRequest(BaseModel):
    scope: str  # employee|team
    id: uuid.UUID
    day: date | None = None


class AnomalyRequest(BaseModel):
    employee_id: uuid.UUID
    day: date | None = None


class AskRequest(BaseModel):
    question: str


class AIResult(BaseModel):
    job_id: uuid.UUID
    kind: str
    text: str
    facts: dict


async def _record_job(session, principal, kind, result) -> uuid.UUID:
    job = AIJob(
        id=uuid.uuid4(), organization_id=principal.organization_id, kind=kind,
        scope=scope_snapshot(principal), status="completed", result=result,
        requested_by=principal.user_id,
    )
    session.add(job)
    await session.flush()
    return job.id


@router.post("/summary", response_model=AIResult)
async def summary(
    payload: SummaryRequest,
    principal: Principal = Depends(require_permission("ai.use")),
    session: AsyncSession = Depends(get_tenant_session),
):
    day = payload.day or now().date()
    try:
        if payload.scope == "employee":
            emp = await require_employee_in_scope(session, principal, payload.id)
            result = await ai_service.employee_summary(session, principal.organization_id, emp, day)
        elif payload.scope == "team":
            require_team_in_scope(principal, payload.id)
            result = await ai_service.team_summary(session, principal.organization_id, payload.id, day)
        else:
            raise HTTPException(status_code=422, detail="scope must be employee|team")
    except ScopeDenied as e:
        raise HTTPException(status_code=403, detail=str(e))

    job_id = await _record_job(session, principal, "summary", result)
    await session.commit()
    return AIResult(job_id=job_id, kind="summary", text=result["text"], facts=result["facts"])


@router.post("/anomaly", response_model=AIResult)
async def anomaly(
    payload: AnomalyRequest,
    principal: Principal = Depends(require_permission("ai.use")),
    session: AsyncSession = Depends(get_tenant_session),
):
    day = payload.day or now().date()
    try:
        emp = await require_employee_in_scope(session, principal, payload.employee_id)
    except ScopeDenied as e:
        raise HTTPException(status_code=403, detail=str(e))
    result = await ai_service.anomaly(session, principal.organization_id, emp, day)
    job_id = await _record_job(session, principal, "anomaly", result)
    await session.commit()
    return AIResult(job_id=job_id, kind="anomaly", text=result["text"], facts=result["facts"])


@router.post("/ask", response_model=AIResult)
async def ask(
    payload: AskRequest,
    principal: Principal = Depends(require_permission("ai.use")),
    session: AsyncSession = Depends(get_tenant_session),
):
    result = await nl.answer(session, principal, payload.question, now().date())
    job_id = await _record_job(session, principal, "nl_query", result)
    await session.commit()
    return AIResult(job_id=job_id, kind="nl_query", text=result["text"], facts=result["facts"])
