"""Agent enrollment + device-token issuance (spec 16, doc 03 §3).

Flow:
  1. Employee (user token) calls POST /auth/agent/enroll -> creates a PENDING device.
  2. Admin approves the device (POST /devices/{id}/approve) -> signing_secret returned to admin,
     or surfaced to the agent operator out-of-band. (For self-service tenants, approval can be
     automated by policy; not enabled by default.)
  3. Agent calls POST /auth/agent/token with device_id + signing proof -> device token.

The device token + signing secret together authenticate all later agent calls.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.db import get_session
from app.core.deps import get_principal, get_tenant_session
from app.core.security import (
    create_device_token,
    verify_signature,
)
from app.core.tenant import set_current_org
from app.models.devices import Device
from app.models.directory import Employee
from app.models.organization import Organization

router = APIRouter(prefix="/auth/agent", tags=["agent-auth"])


class EnrollRequest(BaseModel):
    hostname: str | None = None
    os: str | None = None
    os_version: str | None = None
    agent_version: str | None = None


class EnrollResponse(BaseModel):
    device_id: uuid.UUID
    status: str


class TokenRequest(BaseModel):
    organization_slug: str
    device_id: uuid.UUID
    timestamp: str
    signature: str  # HMAC over "TOKEN\n/auth/agent/token\n<timestamp>\nsha256(<device_id>)"


class TokenResponse(BaseModel):
    device_token: str
    employee_id: uuid.UUID


@router.post("/enroll", response_model=EnrollResponse, status_code=201)
async def enroll(
    payload: EnrollRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    """Employee enrolls their own device (self-service). Requires shift.start_own."""
    if not principal.has("shift.start_own"):
        raise HTTPException(status_code=403, detail="not permitted to enroll a device")

    emp = (
        await session.execute(select(Employee).where(Employee.user_id == principal.user_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="no employee linked to this user")

    device = Device(
        id=uuid.uuid4(),
        organization_id=principal.organization_id,
        employee_id=emp.id,
        hostname=payload.hostname,
        os=payload.os,
        os_version=payload.os_version,
        agent_version=payload.agent_version,
        status="pending",
    )
    session.add(device)
    await audit.record(
        session, action="device.enroll.self", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="device", target_id=device.id,
        new_value={"hostname": payload.hostname, "os": payload.os},
    )
    await session.commit()
    return EnrollResponse(device_id=device.id, status=device.status)


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    payload: TokenRequest,
    session: AsyncSession = Depends(get_session),
):
    """Exchange a signing proof for a device token. No user token needed; the HMAC proves
    possession of the approved device's signing secret. The org is resolved from the slug,
    then the session is scoped so RLS applies to the device lookup."""
    org = (
        await session.execute(
            select(Organization).where(Organization.slug == payload.organization_slug)
        )
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=403, detail="device not approved")
    await set_current_org(session, str(org.id))

    device = (
        await session.execute(select(Device).where(Device.id == payload.device_id))
    ).scalar_one_or_none()
    if device is None or device.status != "approved" or not device.signing_secret:
        raise HTTPException(status_code=403, detail="device not approved")

    # Proof body is the device id; signed with the same canonical scheme as request signing.
    if not verify_signature(
        device.signing_secret,
        "TOKEN",
        "/auth/agent/token",
        str(payload.device_id),
        payload.timestamp,
        payload.signature,
    ):
        raise HTTPException(status_code=401, detail="invalid signing proof")

    token = create_device_token(
        str(device.id), str(device.organization_id), str(device.employee_id)
    )
    return TokenResponse(device_token=token, employee_id=device.employee_id)
