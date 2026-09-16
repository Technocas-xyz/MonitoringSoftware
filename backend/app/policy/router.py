"""Policy API: shift/monitoring policy CRUD, assignment, and resolved preview (spec 84)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.models.policy import MonitoringPolicy, PolicyAssignment, ShiftPolicy
from app.policy.resolver import resolve_for_employee_id
from app.policy.schemas import (
    MonitoringPolicyCreate,
    MonitoringPolicyOut,
    PolicyAssignRequest,
    PolicyPreviewResponse,
    ShiftPolicyCreate,
    ShiftPolicyOut,
)

router = APIRouter(tags=["policies"])


@router.post("/shift-policies", response_model=ShiftPolicyOut, status_code=201)
async def create_shift_policy(
    payload: ShiftPolicyCreate,
    principal: Principal = Depends(require_permission("shiftpolicy.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    policy = ShiftPolicy(
        id=uuid.uuid4(), organization_id=principal.organization_id, **payload.model_dump()
    )
    session.add(policy)
    await audit.record(
        session, action="shiftpolicy.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="shift_policy", target_id=policy.id,
        new_value={"name": policy.name},
    )
    await session.commit()
    return ShiftPolicyOut.model_validate(policy)


@router.get("/shift-policies", response_model=list[ShiftPolicyOut])
async def list_shift_policies(
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(ShiftPolicy))).scalars().all()
    return [ShiftPolicyOut.model_validate(p) for p in rows]


@router.post("/monitoring-policies", response_model=MonitoringPolicyOut, status_code=201)
async def create_monitoring_policy(
    payload: MonitoringPolicyCreate,
    principal: Principal = Depends(require_permission("monitoringpolicy.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    policy = MonitoringPolicy(
        id=uuid.uuid4(), organization_id=principal.organization_id, **payload.model_dump()
    )
    session.add(policy)
    await audit.record(
        session, action="monitoringpolicy.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="monitoring_policy", target_id=policy.id,
        new_value={"name": policy.name},
    )
    await session.commit()
    return MonitoringPolicyOut.model_validate(policy)


@router.get("/monitoring-policies", response_model=list[MonitoringPolicyOut])
async def list_monitoring_policies(
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(MonitoringPolicy))).scalars().all()
    return [MonitoringPolicyOut.model_validate(p) for p in rows]


@router.post("/policies/assign", status_code=201)
async def assign_policy(
    payload: PolicyAssignRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    perm = "shiftpolicy.manage" if payload.policy_kind == "shift" else "monitoringpolicy.manage"
    if not principal.has(perm):
        raise HTTPException(status_code=403, detail=f"missing permission: {perm}")
    if payload.policy_kind not in ("shift", "monitoring"):
        raise HTTPException(status_code=422, detail="policy_kind must be shift|monitoring")

    assignment = PolicyAssignment(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        policy_kind=payload.policy_kind,
        policy_id=payload.policy_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        allow_override=payload.allow_override,
        priority=payload.priority,
    )
    session.add(assignment)
    await audit.record(
        session, action="policy.assign", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="policy_assignment", target_id=assignment.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return {"id": str(assignment.id)}


def _summarize(shift: dict, monitoring: dict) -> list[str]:
    lines = [
        f"Tracking mode: {shift['tracking_mode']}",
        f"Late after: {shift['late_threshold_min']} min",
        f"Break: {'allowed' if shift['allow_break'] else 'not allowed'}"
        + (f", max {shift['max_break_seconds']}s" if shift.get('max_break_seconds') else ""),
        f"Early clock-out: {'allowed' if shift['allow_early_clockout'] else 'blocked'}",
        f"Overtime: {'allowed' if shift['allow_overtime'] else 'no'}"
        + (" (approval required)" if shift.get('overtime_requires_approval') else ""),
        f"Auto start: {shift['auto_start']}, Auto end: {shift['auto_end']}",
        f"Monitoring required: {shift['monitoring_required']}",
        f"Screenshots: {monitoring['screenshot_mode']}"
        + (f" every {monitoring['screenshot_interval_seconds']}s" if monitoring.get('screenshot_interval_seconds') else ""),
        f"Applications: {monitoring['monitor_applications']}, Websites: {monitoring['monitor_websites']} ({monitoring['website_mode']})",
        f"Idle: threshold {monitoring['idle_threshold_seconds']}s, counted as {monitoring['idle_classification']}",
    ]
    return lines


@router.get("/policies/preview", response_model=PolicyPreviewResponse)
async def preview_policy(
    employee_id: uuid.UUID,
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        resolved = await resolve_for_employee_id(session, employee_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="employee not found")
    return PolicyPreviewResponse(
        employee_id=employee_id,
        shift=resolved.shift,
        monitoring=resolved.monitoring,
        summary=_summarize(resolved.shift, resolved.monitoring),
    )
