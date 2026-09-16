"""Analytics API: timeline, dashboards, heatmap, trends (spec 28-33, 87, 88, 102).

Scope narrowing: callers without org-wide roles are restricted to their scoped teams. The
overview aggregates only the caller's visible employees; per-employee/department endpoints
verify the target is within scope.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import dashboards, heatmap_trends
from app.analytics.timeline import build_timeline
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.time_authority import now
from app.models.directory import Employee

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _today() -> date:
    return now().date()


async def _visible_team_ids(principal: Principal) -> set[uuid.UUID] | None:
    """None => org-wide; otherwise the set of team ids the principal may see."""
    if principal.is_org_wide:
        return None
    return set(principal.scoped_team_ids)


async def _employee_in_scope(session, principal, employee_id) -> bool:
    if principal.is_org_wide:
        return True
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        return False
    if emp.user_id == principal.user_id:
        return True  # self
    return emp.team_id in principal.scoped_team_ids


@router.get("/overview")
async def get_overview(
    day: date | None = None,
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    team_ids = await _visible_team_ids(principal)
    return await dashboards.overview(session, principal.organization_id, day or _today(), team_ids)


@router.get("/employees/{employee_id}/detail")
async def get_employee_detail(
    employee_id: uuid.UUID,
    day: date | None = None,
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not await _employee_in_scope(session, principal, employee_id):
        raise HTTPException(status_code=403, detail="employee out of scope")
    return await dashboards.employee_detail(
        session, principal.organization_id, employee_id, day or _today()
    )


@router.get("/employees/{employee_id}/timeline")
async def get_timeline(
    employee_id: uuid.UUID,
    day: date | None = None,
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not await _employee_in_scope(session, principal, employee_id):
        raise HTTPException(status_code=403, detail="employee out of scope")
    entries = await build_timeline(
        session, principal.organization_id, employee_id, day or _today()
    )
    return [
        {"at": e.at.isoformat(), "kind": e.kind, "label": e.label, "detail": e.detail}
        for e in entries
    ]


@router.get("/employees/{employee_id}/heatmap")
async def get_heatmap(
    employee_id: uuid.UUID,
    day: date | None = None,
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not await _employee_in_scope(session, principal, employee_id):
        raise HTTPException(status_code=403, detail="employee out of scope")
    return await heatmap_trends.activity_heatmap(
        session, principal.organization_id, employee_id, day or _today()
    )


@router.get("/employees/{employee_id}/trend")
async def get_employee_trend(
    employee_id: uuid.UUID,
    range: str = "this_week",
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not await _employee_in_scope(session, principal, employee_id):
        raise HTTPException(status_code=403, detail="employee out of scope")
    return await heatmap_trends.employee_trend(
        session, principal.organization_id, employee_id, range, _today()
    )


@router.get("/departments/{department_id}/analytics")
async def get_department_analytics(
    department_id: uuid.UUID,
    day: date | None = None,
    principal: Principal = Depends(require_permission("analytics.org")),
    session: AsyncSession = Depends(get_tenant_session),
):
    return await dashboards.department_analytics(
        session, principal.organization_id, department_id, day or _today()
    )


@router.get("/teams/{team_id}/trend")
async def get_team_trend(
    team_id: uuid.UUID,
    range: str = "this_week",
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not principal.has("analytics.view"):
        raise HTTPException(status_code=403, detail="missing permission: analytics.view")
    if not principal.is_org_wide and team_id not in principal.scoped_team_ids:
        raise HTTPException(status_code=403, detail="team out of scope")
    return await heatmap_trends.team_trend(
        session, principal.organization_id, team_id, range, _today()
    )
