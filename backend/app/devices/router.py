"""Devices API skeleton (spec 42).

Enrollment creates a pending device. An admin/HR approves or revokes. Approval + revocation
are audited. Full device-token issuance and request signing arrive with the desktop agent
in Phase 3; this establishes the lifecycle and RBAC now.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.core.security import new_signing_secret
from app.core.time_authority import now
from app.devices.schemas import DeviceApproveOut, DeviceEnrollRequest, DeviceOut
from app.models.devices import Device
from app.models.directory import Employee

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", response_model=DeviceOut, status_code=201)
async def enroll_device(
    payload: DeviceEnrollRequest,
    principal: Principal = Depends(require_permission("device.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = (
        await session.execute(select(Employee).where(Employee.id == payload.employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="employee not found")

    device = Device(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        employee_id=payload.employee_id,
        hostname=payload.hostname,
        os=payload.os,
        os_version=payload.os_version,
        agent_version=payload.agent_version,
        status="pending",
    )
    session.add(device)
    await audit.record(
        session,
        action="device.enroll",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="device",
        target_id=device.id,
        new_value={"employee_id": str(payload.employee_id), "hostname": payload.hostname},
    )
    await session.commit()
    return DeviceOut.model_validate(device)


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    principal: Principal = Depends(require_permission("device.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(Device))).scalars().all()
    return [DeviceOut.model_validate(d) for d in rows]


async def _get_device(session: AsyncSession, device_id: uuid.UUID) -> Device:
    device = (
        await session.execute(select(Device).where(Device.id == device_id))
    ).scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return device


@router.post("/{device_id}/approve", response_model=DeviceApproveOut)
async def approve_device(
    device_id: uuid.UUID,
    principal: Principal = Depends(require_permission("device.approve")),
    session: AsyncSession = Depends(get_tenant_session),
):
    device = await _get_device(session, device_id)
    old = device.status
    device.status = "approved"
    device.approved_at = now()
    device.revoked_at = None
    # Issue a signing secret on approval. Returned ONCE here; the agent stores it (DPAPI).
    secret = new_signing_secret()
    device.signing_secret = secret
    await audit.record(
        session,
        action="device.approve",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="device",
        target_id=device.id,
        old_value={"status": old},
        new_value={"status": "approved"},
    )
    await session.commit()
    out = DeviceApproveOut.model_validate(device)
    out.signing_secret = secret
    return out


@router.post("/{device_id}/revoke", response_model=DeviceOut)
async def revoke_device(
    device_id: uuid.UUID,
    principal: Principal = Depends(require_permission("device.revoke")),
    session: AsyncSession = Depends(get_tenant_session),
):
    device = await _get_device(session, device_id)
    old = device.status
    device.status = "revoked"
    device.revoked_at = now()
    device.signing_secret = None  # invalidate signing on revocation
    await audit.record(
        session,
        action="device.revoke",
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        target_type="device",
        target_id=device.id,
        old_value={"status": old},
        new_value={"status": "revoked"},
    )
    await session.commit()
    return DeviceOut.model_validate(device)
