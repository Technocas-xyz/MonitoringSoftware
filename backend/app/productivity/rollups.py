"""Daily rollup computation (spec 27/31, doc 02 §14).

Aggregates a day's classified activity per employee, then rolls up to team and department.
Dashboards read these precomputed rollups instead of scanning raw events (doc 00 C2).

Per employee for a work_date:
  - Sum application + website event durations, classifying each app/domain (scoped) into
    productive/neutral/unproductive seconds.
  - tracked_seconds = productive + neutral + unproductive.
  - idle_seconds + worked_seconds come from the derived attendance row for that day.
  - productivity_indicator = configurable weighted ratio over classified seconds.

All values derive from authoritative event + attendance data (spec 54).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directory import Employee
from app.models.monitoring import ApplicationEvent, WebsiteEvent
from app.models.productivity import (
    DailyDepartmentRollup,
    DailyEmployeeRollup,
    DailyTeamRollup,
)
from app.models.shifts import Attendance
from app.productivity.defaults import NEUTRAL, PRODUCTIVE, UNPRODUCTIVE
from app.productivity.resolver import (
    classify_application,
    classify_website,
    compute_indicator,
    load_category_weights,
)
from app.productivity.service import category_id_to_key


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


async def compute_employee_rollup(
    session: AsyncSession, org_id: uuid.UUID, employee: Employee, day: date
) -> DailyEmployeeRollup:
    start, end = _day_bounds(day)
    id_to_key = await category_id_to_key(session, org_id)
    weights = await load_category_weights(session, org_id)

    seconds_by_cat: dict[str, int] = {PRODUCTIVE: 0, NEUTRAL: 0, UNPRODUCTIVE: 0}

    # Application events
    app_events = (
        await session.execute(
            select(ApplicationEvent).where(
                ApplicationEvent.organization_id == org_id,
                ApplicationEvent.employee_id == employee.id,
                ApplicationEvent.occurred_at >= start,
                ApplicationEvent.occurred_at <= end,
            )
        )
    ).scalars().all()
    for ev in app_events:
        cat = await classify_application(
            session, org_id, ev.application, employee.team_id, employee.department_id, id_to_key
        )
        seconds_by_cat[cat] = seconds_by_cat.get(cat, 0) + int(ev.duration_seconds or 0)

    # Website events
    web_events = (
        await session.execute(
            select(WebsiteEvent).where(
                WebsiteEvent.organization_id == org_id,
                WebsiteEvent.employee_id == employee.id,
                WebsiteEvent.occurred_at >= start,
                WebsiteEvent.occurred_at <= end,
            )
        )
    ).scalars().all()
    for ev in web_events:
        cat = await classify_website(
            session, org_id, ev.domain, employee.team_id, employee.department_id, id_to_key
        )
        seconds_by_cat[cat] = seconds_by_cat.get(cat, 0) + int(ev.duration_seconds or 0)

    tracked = sum(seconds_by_cat.values())
    indicator = compute_indicator(seconds_by_cat, weights)

    # Idle + worked from attendance for the day (may be absent).
    att = (
        await session.execute(
            select(Attendance).where(
                Attendance.organization_id == org_id,
                Attendance.employee_id == employee.id,
                Attendance.work_date == day,
            )
        )
    ).scalar_one_or_none()
    idle_seconds = att.idle_seconds if att else 0
    worked_seconds = att.worked_seconds if att else 0

    rollup = (
        await session.execute(
            select(DailyEmployeeRollup).where(
                DailyEmployeeRollup.organization_id == org_id,
                DailyEmployeeRollup.employee_id == employee.id,
                DailyEmployeeRollup.work_date == day,
            )
        )
    ).scalar_one_or_none()
    if rollup is None:
        rollup = DailyEmployeeRollup(
            organization_id=org_id, employee_id=employee.id, work_date=day
        )
        session.add(rollup)

    rollup.tracked_seconds = tracked
    rollup.productive_seconds = seconds_by_cat[PRODUCTIVE]
    rollup.neutral_seconds = seconds_by_cat[NEUTRAL]
    rollup.unproductive_seconds = seconds_by_cat[UNPRODUCTIVE]
    rollup.idle_seconds = idle_seconds
    rollup.worked_seconds = worked_seconds
    rollup.productivity_indicator = indicator
    await session.flush()
    return rollup


async def compute_org_rollups(session: AsyncSession, org_id: uuid.UUID, day: date) -> int:
    """Compute employee rollups for all active employees, then aggregate team + dept rollups."""
    employees = (
        await session.execute(
            select(Employee).where(
                Employee.organization_id == org_id, Employee.status == "active"
            )
        )
    ).scalars().all()

    emp_rollups: list[DailyEmployeeRollup] = []
    for emp in employees:
        emp_rollups.append(await compute_employee_rollup(session, org_id, emp, day))

    weights = await load_category_weights(session, org_id)
    # Aggregate to team/department.
    await _aggregate_group(
        session, org_id, day, emp_rollups, employees, weights,
        key_fn=lambda e: e.team_id, model=DailyTeamRollup, id_field="team_id",
    )
    await _aggregate_group(
        session, org_id, day, emp_rollups, employees, weights,
        key_fn=lambda e: e.department_id, model=DailyDepartmentRollup, id_field="department_id",
    )
    await session.flush()
    return len(emp_rollups)


async def _aggregate_group(
    session, org_id, day, emp_rollups, employees, weights, *, key_fn, model, id_field
):
    emp_by_id = {e.id: e for e in employees}
    groups: dict[uuid.UUID, list[DailyEmployeeRollup]] = {}
    for r in emp_rollups:
        emp = emp_by_id.get(r.employee_id)
        if emp is None:
            continue
        gid = key_fn(emp)
        if gid is None:
            continue
        groups.setdefault(gid, []).append(r)

    for gid, rows in groups.items():
        tracked = sum(r.tracked_seconds for r in rows)
        prod = sum(r.productive_seconds for r in rows)
        neu = sum(r.neutral_seconds for r in rows)
        unp = sum(r.unproductive_seconds for r in rows)
        idle = sum(r.idle_seconds for r in rows)
        indicator = compute_indicator(
            {PRODUCTIVE: prod, NEUTRAL: neu, UNPRODUCTIVE: unp}, weights
        )

        existing = (
            await session.execute(
                select(model).where(
                    model.organization_id == org_id,
                    getattr(model, id_field) == gid,
                    model.work_date == day,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = model(**{"organization_id": org_id, id_field: gid, "work_date": day})
            session.add(existing)
        existing.employees = len(rows)
        existing.tracked_seconds = tracked
        existing.productive_seconds = prod
        existing.neutral_seconds = neu
        existing.unproductive_seconds = unp
        existing.idle_seconds = idle
        existing.productivity_indicator = indicator
    await session.flush()
