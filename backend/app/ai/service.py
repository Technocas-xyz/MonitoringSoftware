"""AI service: gather RBAC-scoped facts, then hand them to the provider (spec 47/89/90).

All gathering happens after scope has been verified for the target. The provider only ever
receives the computed `facts` dict — it never touches the database — so the RBAC boundary is
enforced regardless of which provider is configured.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.models.monitoring import ApplicationEvent
from app.models.productivity import DailyEmployeeRollup, DailyTeamRollup
from app.models.shifts import Attendance


def _day_bounds(day: date):
    return (
        datetime.combine(day, time.min, tzinfo=timezone.utc),
        datetime.combine(day, time.max, tzinfo=timezone.utc),
    )


async def _top_applications(session, org_id, employee_id, day) -> list[dict]:
    start, end = _day_bounds(day)
    rows = (
        await session.execute(
            select(ApplicationEvent.application, func.sum(ApplicationEvent.duration_seconds))
            .where(
                ApplicationEvent.organization_id == org_id,
                ApplicationEvent.employee_id == employee_id,
                ApplicationEvent.occurred_at >= start,
                ApplicationEvent.occurred_at <= end,
            )
            .group_by(ApplicationEvent.application)
            .order_by(func.sum(ApplicationEvent.duration_seconds).desc())
            .limit(5)
        )
    ).all()
    return [{"name": app, "seconds": int(sec or 0)} for app, sec in rows]


async def employee_summary(session: AsyncSession, org_id, employee, day: date) -> dict:
    roll = (
        await session.execute(
            select(DailyEmployeeRollup).where(
                DailyEmployeeRollup.organization_id == org_id,
                DailyEmployeeRollup.employee_id == employee.id,
                DailyEmployeeRollup.work_date == day,
            )
        )
    ).scalar_one_or_none()
    att = (
        await session.execute(
            select(Attendance).where(
                Attendance.organization_id == org_id,
                Attendance.employee_id == employee.id,
                Attendance.work_date == day,
            )
        )
    ).scalar_one_or_none()

    facts = {
        "subject": employee.full_name,
        "worked_seconds": (roll.worked_seconds if roll else (att.worked_seconds if att else 0)),
        "idle_seconds": roll.idle_seconds if roll else (att.idle_seconds if att else 0),
        "indicator": float(roll.productivity_indicator) if roll else None,
        "top_applications": await _top_applications(session, org_id, employee.id, day),
    }
    return {"facts": facts, "text": get_provider().summarize(facts)}


async def team_summary(session: AsyncSession, org_id, team_id, day: date) -> dict:
    # trailing-week team indicator + today
    roll = (
        await session.execute(
            select(DailyTeamRollup).where(
                DailyTeamRollup.organization_id == org_id,
                DailyTeamRollup.team_id == team_id,
                DailyTeamRollup.work_date == day,
            )
        )
    ).scalar_one_or_none()
    week_rows = (
        await session.execute(
            select(DailyTeamRollup).where(
                DailyTeamRollup.organization_id == org_id,
                DailyTeamRollup.team_id == team_id,
                DailyTeamRollup.work_date >= day - timedelta(days=7),
                DailyTeamRollup.work_date < day,
            )
        )
    ).scalars().all()
    prev_avg = (
        round(sum(float(r.productivity_indicator) for r in week_rows) / len(week_rows), 1)
        if week_rows else None
    )
    facts = {
        "subject": "The team",
        "worked_seconds": 0,
        "indicator": float(roll.productivity_indicator) if roll else None,
        "previous_week_indicator": prev_avg,
        "top_applications": [],
    }
    text = get_provider().summarize(facts)
    if prev_avg is not None and roll is not None:
        delta = round(float(roll.productivity_indicator) - prev_avg, 1)
        direction = "higher" if delta >= 0 else "lower"
        text += f" This is approximately {abs(delta)}% {direction} than the prior week."
    return {"facts": facts, "text": text}


async def _app_mix(session, org_id, employee_id, start_day, end_day) -> dict[str, float]:
    start, _ = _day_bounds(start_day)
    _, end = _day_bounds(end_day)
    rows = (
        await session.execute(
            select(ApplicationEvent.application, func.sum(ApplicationEvent.duration_seconds))
            .where(
                ApplicationEvent.organization_id == org_id,
                ApplicationEvent.employee_id == employee_id,
                ApplicationEvent.occurred_at >= start,
                ApplicationEvent.occurred_at <= end,
            )
            .group_by(ApplicationEvent.application)
        )
    ).all()
    total = sum(int(sec or 0) for _, sec in rows) or 1
    return {app: round(100.0 * int(sec or 0) / total, 1) for app, sec in rows}


async def anomaly(session: AsyncSession, org_id, employee, day: date, *, threshold_pct: float = 25.0) -> dict:
    """Compare today's app mix against a trailing 7-day baseline; flag large shifts."""
    today = await _app_mix(session, org_id, employee.id, day, day)
    baseline = await _app_mix(session, org_id, employee.id, day - timedelta(days=7), day - timedelta(days=1))

    changes = []
    for app, today_pct in today.items():
        base_pct = baseline.get(app, 0.0)
        if abs(today_pct - base_pct) >= threshold_pct:
            changes.append({
                "name": app,
                "today_pct": today_pct,
                "baseline_pct": base_pct,
                "direction": "rose" if today_pct > base_pct else "fell",
            })
    changes.sort(key=lambda c: abs(c["today_pct"] - c["baseline_pct"]), reverse=True)
    facts = {"anomalous": bool(changes), "changes": changes}
    return {"facts": facts, "text": get_provider().explain_anomaly(facts)}
