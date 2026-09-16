"""Webhooks API (spec 78): registration + test emit."""
from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.alerts import Webhook
from app.webhooks.service import WEBHOOK_EVENTS, emit

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookCreate(BaseModel):
    url: str
    events: list[str] = Field(default_factory=list)


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    url: str
    events: list
    enabled: bool


class WebhookCreated(WebhookOut):
    secret: str  # returned once at creation


@router.post("", response_model=WebhookCreated, status_code=201)
async def create_webhook(
    payload: WebhookCreate,
    principal: Principal = Depends(require_permission("webhook.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    invalid = set(payload.events) - WEBHOOK_EVENTS
    if invalid:
        raise HTTPException(status_code=422, detail=f"unknown events: {sorted(invalid)}")
    secret = secrets.token_hex(24)
    hook = Webhook(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        url=payload.url, secret=secret, events=payload.events, enabled=True,
    )
    session.add(hook)
    await audit.record(
        session, action="webhook.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="webhook", target_id=hook.id,
        new_value={"url": hook.url, "events": hook.events},
    )
    await session.commit()
    out = WebhookCreated.model_validate(hook)
    out.secret = secret
    return out


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    principal: Principal = Depends(require_permission("webhook.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(Webhook))).scalars().all()
    return [WebhookOut.model_validate(w) for w in rows]


@router.post("/{webhook_id}/test", status_code=202)
async def test_webhook(
    webhook_id: uuid.UUID,
    principal: Principal = Depends(require_permission("webhook.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    hook = (await session.execute(select(Webhook).where(Webhook.id == webhook_id))).scalar_one_or_none()
    if hook is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    # Queue a test delivery using the first subscribed event (or alert.created).
    event = (hook.events or ["alert.created"])[0]
    queued = await emit(session, principal.organization_id, event, {"test": True})
    await session.commit()
    return {"queued": queued}
