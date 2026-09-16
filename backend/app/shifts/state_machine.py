"""Shift state machine service (docs/04).

Server-authoritative transitions. The client requests an action; this service validates it
against the shift's frozen policy snapshot and server time, records an idempotent
`shift_event`, updates state under an optimistic-lock version check, and writes audit.

Nothing here trusts client time for truth: `occurred_at` is always server time (spec 15/100).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.time_authority import now, to_utc
from app.models.shifts import (
    ACTIVE_STATES,
    AUTO_COMPLETED,
    AVAILABLE,
    COMPLETED,
    FORCE_STOPPED,
    MISSED,
    ON_BREAK,
    PAUSED,
    SCHEDULED,
    TERMINAL_STATES,
    WORKING,
    Break,
    Shift,
    ShiftEvent,
)
from app.shifts import errors

# Event type constants
EV_SHIFT_START = "SHIFT_START"
EV_AUTO_START = "AUTO_START"
EV_BREAK_START = "BREAK_START"
EV_BREAK_END = "BREAK_END"
EV_PAUSE = "PAUSE"
EV_RESUME = "RESUME"
EV_SHIFT_END = "SHIFT_END"
EV_AUTO_END = "AUTO_END"
EV_FORCE_STOP = "FORCE_STOP"


def _event_key(shift_id: uuid.UUID, kind: str, provided: str | None) -> str:
    """Idempotency key: use client-provided event_id when present, else derive one."""
    if provided:
        return provided
    return f"{shift_id}:{kind}:{now().timestamp()}"


async def _existing_event(session: AsyncSession, org_id: uuid.UUID, key: str) -> ShiftEvent | None:
    return (
        await session.execute(
            select(ShiftEvent).where(
                ShiftEvent.organization_id == org_id, ShiftEvent.event_key == key
            )
        )
    ).scalar_one_or_none()


async def _record_event(
    session: AsyncSession,
    shift: Shift,
    kind: str,
    *,
    source: str,
    key: str,
    actor_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    client_time: datetime | None = None,
    metadata: dict | None = None,
    occurred_at: datetime | None = None,
) -> ShiftEvent:
    ev = ShiftEvent(
        id=uuid.uuid4(),
        organization_id=shift.organization_id,
        shift_id=shift.id,
        type=kind,
        occurred_at=occurred_at or now(),
        client_time=to_utc(client_time) if client_time else None,
        source=source,
        actor_user_id=actor_user_id,
        device_id=device_id,
        event_metadata=metadata or {},
        event_key=key,
    )
    session.add(ev)
    return ev


def _bump(shift: Shift, new_state: str) -> None:
    shift.state = new_state
    shift.version = (shift.version or 0) + 1


async def start(
    session: AsyncSession,
    shift: Shift,
    *,
    source: str = "employee",
    actor_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    client_time: datetime | None = None,
    event_id: str | None = None,
    auto: bool = False,
) -> Shift:
    """AVAILABLE|SCHEDULED -> WORKING."""
    key = _event_key(shift.id, EV_AUTO_START if auto else EV_SHIFT_START, event_id)
    dup = await _existing_event(session, shift.organization_id, key)
    if dup:
        return shift  # idempotent replay

    if shift.state in TERMINAL_STATES:
        raise errors.InvalidTransition(f"shift is {shift.state}")
    if shift.state not in (SCHEDULED, AVAILABLE):
        raise errors.InvalidTransition(f"cannot start from {shift.state}")

    policy = shift.policy_snapshot or {}
    server_now = now()

    if not auto:
        # Window guard (spec 10): server time within [scheduled_start - earliest, scheduled_start + latest]
        if shift.scheduled_start is not None:
            earliest_min = policy.get("earliest_clock_in_min")
            latest_min = policy.get("latest_clock_in_min")
            sched = to_utc(shift.scheduled_start)
            if earliest_min is not None:
                if server_now < sched - timedelta(minutes=earliest_min):
                    raise errors.WindowNotOpen("clock-in window not open yet")
            if latest_min is not None:
                if server_now > sched + timedelta(minutes=latest_min):
                    raise errors.WindowNotOpen("clock-in window has closed")

    shift.actual_start = server_now
    _bump(shift, WORKING)
    await _record_event(
        session, shift, EV_AUTO_START if auto else EV_SHIFT_START,
        source="system" if auto else source, key=key,
        actor_user_id=actor_user_id, device_id=device_id, client_time=client_time,
        occurred_at=server_now,
    )
    await audit.record(
        session, action="shift.start" + (".auto" if auto else ""),
        organization_id=shift.organization_id, actor_user_id=actor_user_id,
        target_type="shift", target_id=shift.id,
        old_value={"state": AVAILABLE}, new_value={"state": WORKING},
    )
    return shift


async def pause(
    session: AsyncSession,
    shift: Shift,
    *,
    is_break: bool = True,
    actor_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    client_time: datetime | None = None,
    event_id: str | None = None,
) -> Shift:
    """WORKING -> ON_BREAK (break) or PAUSED (non-break)."""
    kind = EV_BREAK_START if is_break else EV_PAUSE
    key = _event_key(shift.id, kind, event_id)
    if await _existing_event(session, shift.organization_id, key):
        return shift

    if shift.state != WORKING:
        raise errors.InvalidTransition(f"cannot pause from {shift.state}")

    policy = shift.policy_snapshot or {}
    server_now = now()

    if is_break:
        if not policy.get("allow_break", True):
            raise errors.NotPermitted("breaks are not allowed by policy")
        if not policy.get("allow_multiple_breaks", True):
            prior = (
                await session.execute(select(Break).where(Break.shift_id == shift.id))
            ).scalars().all()
            if prior:
                raise errors.NotPermitted("multiple breaks are not allowed by policy")
        session.add(
            Break(
                id=uuid.uuid4(),
                organization_id=shift.organization_id,
                shift_id=shift.id,
                started_at=server_now,
                max_seconds=policy.get("max_break_seconds"),
            )
        )
        _bump(shift, ON_BREAK)
    else:
        _bump(shift, PAUSED)

    await _record_event(
        session, shift, kind, source="employee", key=key,
        actor_user_id=actor_user_id, device_id=device_id, client_time=client_time,
        occurred_at=server_now,
    )
    await audit.record(
        session, action="shift.pause",
        organization_id=shift.organization_id, actor_user_id=actor_user_id,
        target_type="shift", target_id=shift.id,
        old_value={"state": WORKING}, new_value={"state": shift.state},
    )
    return shift


async def resume(
    session: AsyncSession,
    shift: Shift,
    *,
    actor_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    client_time: datetime | None = None,
    event_id: str | None = None,
) -> Shift:
    """ON_BREAK|PAUSED -> WORKING."""
    key = _event_key(shift.id, EV_RESUME, event_id)
    if await _existing_event(session, shift.organization_id, key):
        return shift

    if shift.state not in (ON_BREAK, PAUSED):
        raise errors.InvalidTransition(f"cannot resume from {shift.state}")

    server_now = now()

    if shift.state == ON_BREAK:
        open_break = (
            await session.execute(
                select(Break).where(Break.shift_id == shift.id, Break.ended_at.is_(None))
            )
        ).scalars().first()
        if open_break:
            open_break.ended_at = server_now
            if open_break.max_seconds is not None:
                elapsed = (server_now - to_utc(open_break.started_at)).total_seconds()
                if elapsed > open_break.max_seconds:
                    open_break.exceeded = True
        await _record_event(
            session, shift, EV_BREAK_END, source="employee",
            key=_event_key(shift.id, EV_BREAK_END, (event_id + ":be") if event_id else None),
            actor_user_id=actor_user_id, device_id=device_id, occurred_at=server_now,
        )

    _bump(shift, WORKING)
    await _record_event(
        session, shift, EV_RESUME, source="employee", key=key,
        actor_user_id=actor_user_id, device_id=device_id, client_time=client_time,
        occurred_at=server_now,
    )
    await audit.record(
        session, action="shift.resume",
        organization_id=shift.organization_id, actor_user_id=actor_user_id,
        target_type="shift", target_id=shift.id, new_value={"state": WORKING},
    )
    return shift


async def end(
    session: AsyncSession,
    shift: Shift,
    *,
    source: str = "employee",
    actor_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    client_time: datetime | None = None,
    event_id: str | None = None,
    auto: bool = False,
    forced: bool = False,
    reason: str | None = None,
) -> Shift:
    """WORKING|ON_BREAK|PAUSED -> COMPLETED|AUTO_COMPLETED|FORCE_STOPPED."""
    if forced:
        kind, target_state, action = EV_FORCE_STOP, FORCE_STOPPED, "shift.force_stop"
    elif auto:
        kind, target_state, action = EV_AUTO_END, AUTO_COMPLETED, "shift.end.auto"
    else:
        kind, target_state, action = EV_SHIFT_END, COMPLETED, "shift.end"

    key = _event_key(shift.id, kind, event_id)
    if await _existing_event(session, shift.organization_id, key):
        return shift

    if shift.state not in ACTIVE_STATES or shift.state == AVAILABLE:
        raise errors.InvalidTransition(f"cannot end from {shift.state}")

    policy = shift.policy_snapshot or {}
    server_now = now()

    # Early clock-out guard (manual end only)
    if not auto and not forced and shift.scheduled_end is not None:
        if server_now < to_utc(shift.scheduled_end) and not policy.get("allow_early_clockout", False):
            raise errors.NotPermitted("early clock-out is not allowed by policy")

    # Close any open break
    open_break = (
        await session.execute(
            select(Break).where(Break.shift_id == shift.id, Break.ended_at.is_(None))
        )
    ).scalars().first()
    if open_break:
        open_break.ended_at = server_now

    shift.actual_end = server_now
    _bump(shift, target_state)
    await _record_event(
        session, shift, kind,
        source="manager" if forced else ("system" if auto else source),
        key=key, actor_user_id=actor_user_id, device_id=device_id, client_time=client_time,
        metadata={"reason": reason} if reason else None, occurred_at=server_now,
    )
    await audit.record(
        session, action=action, organization_id=shift.organization_id,
        actor_user_id=actor_user_id, target_type="shift", target_id=shift.id,
        old_value={"state": WORKING}, new_value={"state": target_state}, reason=reason,
    )
    return shift
