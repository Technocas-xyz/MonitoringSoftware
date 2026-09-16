"""RBAC scope guard for AI (spec 90).

AI must never bypass permissions. Every AI operation resolves the target within the caller's
authorization scope BEFORE any data is gathered; out-of-scope targets raise ScopeDenied. The
gathered facts are the only thing handed to the provider, so even an external LLM cannot see
unauthorized data.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.models.directory import Employee


class ScopeDenied(Exception):
    pass


async def require_employee_in_scope(
    session: AsyncSession, principal: Principal, employee_id: uuid.UUID
) -> Employee:
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise ScopeDenied("employee not found")
    if principal.is_org_wide:
        return emp
    # self
    if emp.user_id == principal.user_id:
        return emp
    # scoped teams
    if emp.team_id is not None and emp.team_id in principal.scoped_team_ids:
        return emp
    raise ScopeDenied("employee is outside your authorization scope")


def require_team_in_scope(principal: Principal, team_id: uuid.UUID) -> None:
    if principal.is_org_wide:
        return
    if team_id in principal.scoped_team_ids:
        return
    raise ScopeDenied("team is outside your authorization scope")


def scope_snapshot(principal: Principal) -> dict:
    """Serialize the caller's scope for the ai_jobs.scope audit column."""
    return {
        "org_wide": principal.is_org_wide,
        "team_ids": [str(t) for t in principal.scoped_team_ids],
        "department_ids": [str(d) for d in principal.scoped_department_ids],
        "user_id": str(principal.user_id),
    }
