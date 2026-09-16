"""Natural-language analytics (spec 89/90).

A small, bounded intent parser resolves a question to a metric computed strictly within the
caller's authorization scope. It never runs free-form queries; unrecognized questions return a
safe fallback. The computed answer is passed to the provider as a fact, so the RBAC boundary
holds even with an external LLM.

Supported intents (scoped to the caller's visible employees/teams):
  - highest productive activity this week (department/team)
  - most overtime (employee)
  - most time-consuming applications
  - highest attendance (team)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_provider
from app.auth.principal import Principal
from app.models.directory import Employee
from app.models.monitoring import ApplicationEvent
from app.models.productivity import DailyEmployeeRollup, DailyTeamRollup


async def _visible_employee_ids(session: AsyncSession, principal: Principal) -> list[uuid.UUID]:
    stmt = select(Employee).where(Employee.organization_id == principal.organization_id)
    if not principal.is_org_wide:
        if principal.scoped_team_ids:
            stmt = stmt.where(Employee.team_id.in_(principal.scoped_team_ids))
        else:
            stmt = stmt.where(Employee.user_id == principal.user_id)
    return [e.id for e in (await session.execute(stmt)).scalars().all()]


async def answer(session: AsyncSession, principal: Principal, question: str, today: date) -> dict:
    q = question.lower()
    emp_ids = await _visible_employee_ids(session, principal)
    week_start = today - timedelta(days=today.weekday())
    resolved: str | None = None

    if not emp_ids:
        resolved = None

    elif "overtime" in q:
        rows = (
            await session.execute(
                select(DailyEmployeeRollup.employee_id, func.sum(DailyEmployeeRollup.worked_seconds))
                .where(
                    DailyEmployeeRollup.organization_id == principal.organization_id,
                    DailyEmployeeRollup.employee_id.in_(emp_ids),
                    DailyEmployeeRollup.work_date >= week_start,
                )
                .group_by(DailyEmployeeRollup.employee_id)
                .order_by(func.sum(DailyEmployeeRollup.worked_seconds).desc())
                .limit(1)
            )
        ).first()
        if rows:
            resolved = f"Employee {rows[0]} had the most tracked work this week."

    elif "application" in q or "app" in q:
        rows = (
            await session.execute(
                select(ApplicationEvent.application, func.sum(ApplicationEvent.duration_seconds))
                .where(
                    ApplicationEvent.organization_id == principal.organization_id,
                    ApplicationEvent.employee_id.in_(emp_ids),
                )
                .group_by(ApplicationEvent.application)
                .order_by(func.sum(ApplicationEvent.duration_seconds).desc())
                .limit(1)
            )
        ).first()
        if rows:
            resolved = f"{rows[0]} consumed the most time among the data you can view."

    elif "productive" in q or "productivity" in q:
        # Highest average team indicator this week (within visible teams).
        team_filter = None if principal.is_org_wide else list(principal.scoped_team_ids)
        stmt = select(DailyTeamRollup).where(
            DailyTeamRollup.organization_id == principal.organization_id,
            DailyTeamRollup.work_date >= week_start,
        )
        if team_filter is not None:
            if not team_filter:
                stmt = stmt.where(DailyTeamRollup.team_id.is_(None))  # none visible
            else:
                stmt = stmt.where(DailyTeamRollup.team_id.in_(team_filter))
        rows = (await session.execute(stmt)).scalars().all()
        best = {}
        for r in rows:
            best.setdefault(r.team_id, []).append(float(r.productivity_indicator))
        if best:
            ranked = sorted(
                ((tid, sum(v) / len(v)) for tid, v in best.items()), key=lambda x: x[1], reverse=True
            )
            tid, avg = ranked[0]
            resolved = f"Team {tid} had the highest productive activity this week ({round(avg, 1)}%)."

    facts = {"answer": resolved}
    return {"facts": facts, "text": get_provider().answer(question, facts)}
