"""Activity heatmap (spec 87) and trend/comparison analytics (spec 88)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.productivity import DailyEmployeeRollup, DailyTeamRollup


async def activity_heatmap(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, day: date
) -> list[dict]:
    """Hour-by-hour combined activity intensity (0..100) from activity_intervals.

    Each hour bucket averages the combined_pct of intervals starting in that hour; idle
    intervals count as 0. Returns 24 buckets.
    """
    from app.models.monitoring import ActivityInterval

    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    intervals = (
        await session.execute(
            select(ActivityInterval).where(
                ActivityInterval.organization_id == org_id,
                ActivityInterval.employee_id == employee_id,
                ActivityInterval.occurred_at >= start,
                ActivityInterval.occurred_at <= end,
            )
        )
    ).scalars().all()

    buckets: dict[int, list[int]] = {h: [] for h in range(24)}
    for iv in intervals:
        hour = iv.interval_start.astimezone(timezone.utc).hour
        buckets[hour].append(0 if iv.is_idle else int(iv.combined_pct or 0))

    return [
        {"hour": h, "intensity": round(sum(v) / len(v)) if v else 0}
        for h, v in sorted(buckets.items())
    ]


def _range_bounds(range_key: str, today: date) -> tuple[date, date, date, date]:
    """Return (cur_start, cur_end, prev_start, prev_end) for a named range."""
    if range_key == "today":
        return today, today, today - timedelta(days=1), today - timedelta(days=1)
    if range_key == "this_week":
        cur_start = today - timedelta(days=today.weekday())
        return cur_start, today, cur_start - timedelta(days=7), cur_start - timedelta(days=1)
    if range_key == "this_month":
        cur_start = today.replace(day=1)
        prev_end = cur_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
        return cur_start, today, prev_start, prev_end
    # default: last 7 days
    return today - timedelta(days=6), today, today - timedelta(days=13), today - timedelta(days=7)


async def _avg_indicator_employee(session, org_id, emp_id, start, end) -> float:
    rows = (
        await session.execute(
            select(DailyEmployeeRollup).where(
                DailyEmployeeRollup.organization_id == org_id,
                DailyEmployeeRollup.employee_id == emp_id,
                DailyEmployeeRollup.work_date >= start,
                DailyEmployeeRollup.work_date <= end,
            )
        )
    ).scalars().all()
    return round(sum(float(r.productivity_indicator) for r in rows) / len(rows), 2) if rows else 0.0


async def employee_trend(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, range_key: str, today: date
) -> dict:
    cs, ce, ps, pe = _range_bounds(range_key, today)
    current = await _avg_indicator_employee(session, org_id, employee_id, cs, ce)
    previous = await _avg_indicator_employee(session, org_id, employee_id, ps, pe)
    return {
        "range": range_key,
        "current_indicator": current,
        "previous_indicator": previous,
        "delta": round(current - previous, 2),
    }


async def team_trend(
    session: AsyncSession, org_id: uuid.UUID, team_id: uuid.UUID, range_key: str, today: date
) -> dict:
    cs, ce, ps, pe = _range_bounds(range_key, today)

    async def avg(start, end):
        rows = (
            await session.execute(
                select(DailyTeamRollup).where(
                    DailyTeamRollup.organization_id == org_id,
                    DailyTeamRollup.team_id == team_id,
                    DailyTeamRollup.work_date >= start,
                    DailyTeamRollup.work_date <= end,
                )
            )
        ).scalars().all()
        return round(sum(float(r.productivity_indicator) for r in rows) / len(rows), 2) if rows else 0.0

    current = await avg(cs, ce)
    previous = await avg(ps, pe)
    return {
        "range": range_key,
        "current_indicator": current,
        "previous_indicator": previous,
        "delta": round(current - previous, 2),
    }
