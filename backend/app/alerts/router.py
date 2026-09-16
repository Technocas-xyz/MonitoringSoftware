"""Alert rules + alerts + notifications API (spec 35/36/49)."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.time_authority import now
from app.models.alerts import Alert, AlertRule, Notification

router = APIRouter(tags=["alerts"])


class AlertRuleCreate(BaseModel):
    key: str
    enabled: bool = True
    severity: str = "warning"
    scope_type: str = "organization"
    scope_id: uuid.UUID | None = None
    params: dict = Field(default_factory=dict)
    channels: list[str] = Field(default_factory=lambda: ["in_app"])


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    enabled: bool
    severity: str
    params: dict
    channels: list


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rule_id: uuid.UUID | None
    employee_id: uuid.UUID | None
    severity: str
    message: str
    status: str
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    channel: str
    title: str | None
    body: str
    read_at: datetime | None
    created_at: datetime


@router.post("/alert-rules", response_model=AlertRuleOut, status_code=201)
async def create_rule(
    payload: AlertRuleCreate,
    principal: Principal = Depends(require_permission("alert.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rule = AlertRule(
        id=uuid.uuid4(), organization_id=principal.organization_id, **payload.model_dump()
    )
    session.add(rule)
    await audit.record(
        session, action="alert.rule.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="alert_rule", target_id=rule.id,
        new_value={"key": rule.key},
    )
    await session.commit()
    return AlertRuleOut.model_validate(rule)


@router.get("/alert-rules", response_model=list[AlertRuleOut])
async def list_rules(
    principal: Principal = Depends(require_permission("alert.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(AlertRule))).scalars().all()
    return [AlertRuleOut.model_validate(r) for r in rows]


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    principal: Principal = Depends(require_permission("alert.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status == status)
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    stmt = stmt.order_by(Alert.created_at.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()
    return [AlertOut.model_validate(a) for a in rows]


async def _set_alert_status(session, principal, alert_id, status_value, action):
    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = status_value
    await audit.record(
        session, action=action, organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="alert", target_id=alert.id,
        new_value={"status": status_value},
    )
    await session.commit()
    return AlertOut.model_validate(alert)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    principal: Principal = Depends(require_permission("alert.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _set_alert_status(session, principal, alert_id, "acknowledged", "alert.acknowledge")


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: uuid.UUID,
    principal: Principal = Depends(require_permission("alert.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await _set_alert_status(session, principal, alert_id, "resolved", "alert.resolve")


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = (
        select(Notification)
        .where(
            (Notification.recipient_user_id == principal.user_id)
            | (Notification.recipient_user_id.is_(None))
        )
        .order_by(Notification.created_at.desc())
        .limit(200)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [NotificationOut.model_validate(n) for n in rows]


@router.post("/notifications/{notification_id}/read", status_code=204)
async def read_notification(
    notification_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    n = (
        await session.execute(select(Notification).where(Notification.id == notification_id))
    ).scalar_one_or_none()
    if n is None:
        raise HTTPException(status_code=404, detail="notification not found")
    n.read_at = now()
    await session.commit()
