"""Resolve which work schedule applies to an employee on a date, and its occurrences.

Assignment specificity mirrors policy resolution: employee > team > department. Among
matching assignments effective on the date, the most specific (then highest priority) wins.
The effective timezone is employee.timezone or the schedule.timezone or the org timezone.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directory import Employee
from app.models.organization import Organization
from app.models.scheduling import ScheduleAssignment, WorkSchedule
from app.scheduling.occurrences import Occurrence, compute_occurrences

_SPECIFICITY = {"employee": 3, "team": 2, "department": 1}


async def resolve_schedule(
    session: AsyncSession, employee: Employee, day: date
) -> WorkSchedule | None:
    level_target = {
        "employee": employee.id,
        "team": employee.team_id,
        "department": employee.department_id,
    }
    assignments = (
        await session.execute(
            select(ScheduleAssignment).where(
                ScheduleAssignment.organization_id == employee.organization_id
            )
        )
    ).scalars().all()

    matches: list[ScheduleAssignment] = []
    for a in assignments:
        target = level_target.get(a.target_type)
        if target is None or a.target_id != target:
            continue
        if a.effective_from > day:
            continue
        if a.effective_to is not None and a.effective_to < day:
            continue
        matches.append(a)

    if not matches:
        return None

    best = sorted(
        matches,
        key=lambda a: (_SPECIFICITY.get(a.target_type, 0), a.priority),
        reverse=True,
    )[0]
    return (
        await session.execute(select(WorkSchedule).where(WorkSchedule.id == best.schedule_id))
    ).scalar_one_or_none()


async def _effective_tz(session: AsyncSession, employee: Employee, schedule: WorkSchedule) -> str:
    if employee.timezone:
        return employee.timezone
    if schedule.timezone:
        return schedule.timezone
    org = (
        await session.execute(
            select(Organization).where(Organization.id == employee.organization_id)
        )
    ).scalar_one()
    return org.timezone


async def occurrences_for(
    session: AsyncSession, employee: Employee, day: date
) -> tuple[WorkSchedule | None, list[Occurrence], str | None]:
    schedule = await resolve_schedule(session, employee, day)
    if schedule is None:
        return None, [], None
    tz = await _effective_tz(session, employee, schedule)
    return schedule, compute_occurrences(schedule.type, schedule.definition, day, tz), tz
