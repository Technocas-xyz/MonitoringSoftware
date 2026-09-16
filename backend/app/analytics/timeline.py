"""Employee timeline (spec 28): merge shift events + application/website spans chronologically."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import ApplicationEvent, WebsiteEvent
from app.models.shifts import Shift, ShiftEvent


@dataclass
class TimelineEntry:
    at: datetime
    kind: str      # shift|application|website
    label: str
    detail: str | None = None


def _bounds(day: date):
    return (
        datetime.combine(day, time.min, tzinfo=timezone.utc),
        datetime.combine(day, time.max, tzinfo=timezone.utc),
    )


async def build_timeline(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, day: date
) -> list[TimelineEntry]:
    start, end = _bounds(day)
    entries: list[TimelineEntry] = []

    # Shift lifecycle events for shifts on this day.
    shifts = (
        await session.execute(
            select(Shift).where(
                Shift.organization_id == org_id, Shift.employee_id == employee_id
            )
        )
    ).scalars().all()
    shift_ids = [s.id for s in shifts]
    if shift_ids:
        sevents = (
            await session.execute(
                select(ShiftEvent).where(
                    ShiftEvent.shift_id.in_(shift_ids),
                    ShiftEvent.occurred_at >= start,
                    ShiftEvent.occurred_at <= end,
                )
            )
        ).scalars().all()
        for e in sevents:
            entries.append(TimelineEntry(at=e.occurred_at, kind="shift", label=e.type))

    # Application spans.
    apps = (
        await session.execute(
            select(ApplicationEvent).where(
                ApplicationEvent.organization_id == org_id,
                ApplicationEvent.employee_id == employee_id,
                ApplicationEvent.occurred_at >= start,
                ApplicationEvent.occurred_at <= end,
            )
        )
    ).scalars().all()
    for a in apps:
        entries.append(TimelineEntry(
            at=a.started_at, kind="application", label=a.application, detail=a.window_title
        ))

    # Website spans.
    webs = (
        await session.execute(
            select(WebsiteEvent).where(
                WebsiteEvent.organization_id == org_id,
                WebsiteEvent.employee_id == employee_id,
                WebsiteEvent.occurred_at >= start,
                WebsiteEvent.occurred_at <= end,
            )
        )
    ).scalars().all()
    for w in webs:
        entries.append(TimelineEntry(at=w.started_at, kind="website", label=w.domain))

    entries.sort(key=lambda e: e.at)
    return entries
