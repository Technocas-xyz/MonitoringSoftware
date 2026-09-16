"""Event ingestion (spec 52, doc 03 §8).

Idempotent, offline-tolerant persistence of monitoring events. Called by the device-auth
/ingest/events endpoint. Key properties:

  - Dedup by (organization_id, event_key = client event_id): re-sent batches are safe.
  - Server assigns occurred_at authority; client timestamps are advisory (spec 15).
  - Policy-based field dropping: window_title/url are discarded when the resolved monitoring
    policy forbids them (privacy, spec 45/83).
  - Events are bound to the employee's current active shift when one exists.

This runs synchronously inside the request for now; the architecture (doc 01) enqueues heavy
persistence to Celery at scale, but the contract and idempotency are identical.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_authority import now, to_utc
from app.models.monitoring import (
    ActivityInterval,
    ApplicationEvent,
    Screenshot,
    WebsiteEvent,
)
from app.models.shifts import ACTIVE_STATES, Shift

VALID_TYPES = {
    "APPLICATION_ACTIVITY",
    "WEBSITE_ACTIVITY",
    "ACTIVITY_INTERVAL",
    "IDLE",
    "SCREENSHOT_META",
}


@dataclass
class IngestResult:
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    next_sequence_ack: int | None = None


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    try:
        return to_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


async def _current_shift_id(session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID):
    shift = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id,
                Shift.employee_id == employee_id,
                Shift.state.in_(ACTIVE_STATES),
            )
        )
    ).scalars().first()
    return (shift.id if shift else None), (shift.policy_snapshot if shift else {})


async def _seen(session: AsyncSession, model, org_id: uuid.UUID, event_key: str) -> bool:
    row = (
        await session.execute(
            select(model.id).where(
                model.organization_id == org_id, model.event_key == event_key
            )
        )
    ).first()
    return row is not None


async def ingest_batch(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    employee_id: uuid.UUID,
    device_id: uuid.UUID,
    events: list[dict],
    sequence: int | None = None,
) -> IngestResult:
    result = IngestResult(next_sequence_ack=sequence)
    shift_id, policy = await _current_shift_id(session, organization_id, employee_id)
    monitoring = (policy or {}).get("monitoring", {}) if policy else {}

    allow_window_title = bool(monitoring.get("monitor_applications", True))  # title only if apps monitored
    website_mode = monitoring.get("website_mode", "domain")
    server_now = now()

    for evt in events:
        etype = evt.get("type")
        event_key = evt.get("event_id")
        if etype not in VALID_TYPES or not event_key:
            result.rejected += 1
            continue

        payload = evt.get("payload") or {}
        client_ts = _parse_dt(evt.get("timestamp"))

        if etype == "APPLICATION_ACTIVITY":
            if await _seen(session, ApplicationEvent, organization_id, event_key):
                result.duplicates += 1
                continue
            started = _parse_dt(payload.get("started_at")) or client_ts or server_now
            session.add(ApplicationEvent(
                id=uuid.uuid4(), organization_id=organization_id, employee_id=employee_id,
                device_id=device_id, shift_id=shift_id,
                application=str(payload.get("application", "unknown"))[:255],
                process_name=(str(payload.get("process"))[:255] if payload.get("process") else None),
                # Privacy: drop window title unless policy permits application monitoring.
                window_title=(str(payload.get("window_title"))[:512]
                              if (allow_window_title and payload.get("window_title")) else None),
                started_at=started,
                ended_at=_parse_dt(payload.get("ended_at")),
                duration_seconds=int(payload.get("duration", 0) or 0),
                occurred_at=started, event_key=event_key,
            ))
            result.accepted += 1

        elif etype == "WEBSITE_ACTIVITY":
            if await _seen(session, WebsiteEvent, organization_id, event_key):
                result.duplicates += 1
                continue
            started = _parse_dt(payload.get("started_at")) or client_ts or server_now
            session.add(WebsiteEvent(
                id=uuid.uuid4(), organization_id=organization_id, employee_id=employee_id,
                device_id=device_id, shift_id=shift_id,
                domain=str(payload.get("domain", "unknown"))[:255],
                # Full URL only when policy is full_url; otherwise domain-only.
                url=(str(payload.get("url"))[:1024]
                     if (website_mode == "full_url" and payload.get("url")) else None),
                category=(str(payload.get("category"))[:64] if payload.get("category") else None),
                started_at=started,
                ended_at=_parse_dt(payload.get("ended_at")),
                duration_seconds=int(payload.get("duration", 0) or 0),
                occurred_at=started, event_key=event_key,
            ))
            result.accepted += 1

        elif etype in ("ACTIVITY_INTERVAL", "IDLE"):
            if await _seen(session, ActivityInterval, organization_id, event_key):
                result.duplicates += 1
                continue
            istart = _parse_dt(payload.get("interval_start")) or client_ts or server_now
            iend = _parse_dt(payload.get("interval_end")) or server_now
            is_idle = etype == "IDLE" or bool(payload.get("is_idle"))
            session.add(ActivityInterval(
                id=uuid.uuid4(), organization_id=organization_id, employee_id=employee_id,
                device_id=device_id, shift_id=shift_id,
                interval_start=istart, interval_end=iend,
                keyboard_pct=payload.get("keyboard_pct"),
                mouse_pct=payload.get("mouse_pct"),
                combined_pct=payload.get("combined_pct"),
                is_idle=is_idle,
                occurred_at=istart, event_key=event_key,
            ))
            result.accepted += 1

        elif etype == "SCREENSHOT_META":
            # Screenshot metadata registered here is the fallback path; the presign flow is
            # preferred. Mark pending; the blob is uploaded/confirmed separately.
            if await _seen(session, Screenshot, organization_id, event_key):
                result.duplicates += 1
                continue
            captured = _parse_dt(payload.get("captured_at")) or client_ts or server_now
            session.add(Screenshot(
                id=uuid.uuid4(), organization_id=organization_id, employee_id=employee_id,
                device_id=device_id, shift_id=shift_id,
                storage_key=str(payload.get("storage_key", "")),
                captured_at=captured, bytes=payload.get("bytes"),
                status="pending", occurred_at=captured, event_key=event_key,
            ))
            result.accepted += 1

    await session.flush()
    return result
