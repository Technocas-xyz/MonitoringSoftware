"""Policy inheritance resolver (docs/07 §5, spec 7).

Resolves the effective shift + monitoring policy for an employee by walking the specificity
chain organization -> department -> team -> employee. A more specific level overrides an
inherited value only when the *inherited* assignment permits override (`allow_override`);
otherwise the inherited value stands. Ties at the same level break by `priority`.

The result is a plain dict (the "resolved effective policy") returned by /policies/preview
and frozen onto a shift at start.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directory import Employee
from app.models.policy import MonitoringPolicy, PolicyAssignment, ShiftPolicy
from app.policy.defaults import (
    DEFAULT_MONITORING_POLICY,
    DEFAULT_SHIFT_POLICY,
    MONITORING_FIELDS,
    SHIFT_FIELDS,
)

# Specificity order: lower index = more general (applied first, can be overridden by later).
LEVEL_ORDER = ["organization", "department", "team", "employee"]


@dataclass
class ResolvedPolicy:
    shift: dict
    monitoring: dict


def _policy_to_dict(obj, fields: list[str]) -> dict:
    return {f: getattr(obj, f) for f in fields}


async def _load_policy(session: AsyncSession, kind: str, policy_id: uuid.UUID) -> dict | None:
    model = ShiftPolicy if kind == "shift" else MonitoringPolicy
    fields = SHIFT_FIELDS if kind == "shift" else MONITORING_FIELDS
    obj = (await session.execute(select(model).where(model.id == policy_id))).scalar_one_or_none()
    return _policy_to_dict(obj, fields) if obj else None


async def _resolve_kind(
    session: AsyncSession,
    kind: str,
    org_id: uuid.UUID,
    department_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
    employee_id: uuid.UUID,
) -> dict:
    defaults = DEFAULT_SHIFT_POLICY if kind == "shift" else DEFAULT_MONITORING_POLICY

    # Map each level to its concrete target id for this employee.
    level_target: dict[str, uuid.UUID | None] = {
        "organization": org_id,
        "department": department_id,
        "team": team_id,
        "employee": employee_id,
    }

    assignments = (
        await session.execute(
            select(PolicyAssignment).where(
                PolicyAssignment.organization_id == org_id,
                PolicyAssignment.policy_kind == kind,
            )
        )
    ).scalars().all()

    # Index assignments by (level, target_id)
    by_level: dict[str, list[PolicyAssignment]] = {lvl: [] for lvl in LEVEL_ORDER}
    for a in assignments:
        target = level_target.get(a.target_type)
        if target is not None and a.target_id == target:
            by_level[a.target_type].append(a)

    effective = dict(defaults)
    # Track whether the currently-applied source permitted downstream override.
    # Start assuming override is allowed from the implicit default baseline.
    override_allowed_from_prev = True

    for level in LEVEL_ORDER:
        candidates = by_level[level]
        if not candidates:
            continue
        # Highest priority wins at this level.
        chosen = sorted(candidates, key=lambda x: x.priority, reverse=True)[0]
        policy_values = await _load_policy(session, kind, chosen.policy_id)
        if policy_values is None:
            continue
        if override_allowed_from_prev:
            effective.update(policy_values)
        # The chosen assignment decides whether the NEXT (more specific) level may override.
        override_allowed_from_prev = chosen.allow_override

    return effective


async def resolve_for_employee(session: AsyncSession, employee: Employee) -> ResolvedPolicy:
    org_id = employee.organization_id
    shift = await _resolve_kind(
        session, "shift", org_id, employee.department_id, employee.team_id, employee.id
    )
    monitoring = await _resolve_kind(
        session, "monitoring", org_id, employee.department_id, employee.team_id, employee.id
    )
    return ResolvedPolicy(shift=shift, monitoring=monitoring)


async def resolve_for_employee_id(session: AsyncSession, employee_id: uuid.UUID) -> ResolvedPolicy:
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise ValueError("employee not found")
    return await resolve_for_employee(session, emp)
