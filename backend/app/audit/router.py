"""Audit log read API (spec 46). Read-only; there is no write/update/delete endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import uuid
from datetime import datetime

from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.audit import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: uuid.UUID | None
    reason: str | None
    at: datetime


@router.get("", response_model=list[AuditOut])
async def list_audit_logs(
    principal: Principal = Depends(require_permission("audit.view")),
    session: AsyncSession = Depends(get_tenant_session),
    limit: int = 100,
):
    stmt = (
        select(AuditLog)
        .where(AuditLog.organization_id == principal.organization_id)
        .order_by(AuditLog.at.desc())
        .limit(min(limit, 500))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [AuditOut.model_validate(r) for r in rows]
