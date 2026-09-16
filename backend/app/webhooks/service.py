"""Webhook emission + signed delivery (spec 78).

emit() records a WebhookDelivery (pending) for every enabled webhook subscribed to the event.
A worker then delivers each pending row with an HMAC-SHA256 signature over the JSON body,
retrying with attempt counting. Emission is cheap and never blocks the request path.

Events: shift.started, shift.paused, shift.resumed, shift.ended, attendance.late,
attendance.absent, timesheet.approved, alert.created.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time_authority import now
from app.models.alerts import Webhook, WebhookDelivery

log = get_logger("webhooks")

WEBHOOK_EVENTS = {
    "shift.started", "shift.paused", "shift.resumed", "shift.ended",
    "attendance.late", "attendance.absent", "timesheet.approved", "alert.created",
}


def sign_payload(secret: str, body: str) -> str:
    return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


async def emit(session: AsyncSession, org_id: uuid.UUID, event: str, payload: dict) -> int:
    """Queue deliveries for all enabled webhooks subscribed to `event`. Returns count queued."""
    if event not in WEBHOOK_EVENTS:
        return 0
    hooks = (
        await session.execute(
            select(Webhook).where(Webhook.organization_id == org_id, Webhook.enabled.is_(True))
        )
    ).scalars().all()
    queued = 0
    for hook in hooks:
        if event not in (hook.events or []):
            continue
        session.add(WebhookDelivery(
            id=uuid.uuid4(), organization_id=org_id, webhook_id=hook.id,
            event=event, payload=payload, status="pending", attempts=0,
        ))
        queued += 1
    await session.flush()
    return queued


async def deliver_pending(session: AsyncSession, org_id: uuid.UUID, max_attempts: int = 5) -> int:
    """Attempt delivery of pending webhook deliveries. Uses httpx if available; records
    attempts and marks delivered/failed. Signature header: X-RWM-Signature."""
    try:
        import httpx  # type: ignore
    except Exception:
        log.warning("httpx unavailable; skipping webhook delivery")
        return 0

    pending = (
        await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.organization_id == org_id,
                WebhookDelivery.status == "pending",
            ).limit(100)
        )
    ).scalars().all()

    delivered = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for d in pending:
            hook = (
                await session.execute(select(Webhook).where(Webhook.id == d.webhook_id))
            ).scalar_one_or_none()
            if hook is None or not hook.enabled:
                d.status = "failed"
                continue
            body = json.dumps({"event": d.event, "payload": d.payload}, default=str)
            sig = sign_payload(hook.secret, body)
            d.attempts += 1
            d.last_attempt_at = now()
            try:
                resp = await client.post(
                    hook.url, content=body,
                    headers={"Content-Type": "application/json", "X-RWM-Signature": sig,
                             "X-RWM-Event": d.event},
                )
                if 200 <= resp.status_code < 300:
                    d.status = "delivered"
                    delivered += 1
                elif d.attempts >= max_attempts:
                    d.status = "failed"
            except Exception:
                if d.attempts >= max_attempts:
                    d.status = "failed"
    await session.flush()
    return delivered
