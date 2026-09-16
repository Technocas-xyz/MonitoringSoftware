"""Agent (device) authentication dependencies.

An agent request carries:
  Authorization: Bearer <device_token>          (JWT, type=device)
  X-Signature:   <hmac hex>                       (HMAC over method+path+body+timestamp)
  X-Timestamp:   <unix seconds>

The device token identifies device/org/employee; the HMAC (keyed by the device's
signing_secret) proves the request came from the enrolled device and was not tampered with.
Stale timestamps are rejected to limit replay. Only APPROVED devices are accepted.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import DEVICE, TokenError, decode_token_of_type, verify_signature
from app.core.tenant import open_tenant_session
from app.models.devices import Device

_bearer = HTTPBearer(auto_error=True)

# Max allowed clock skew for the signed timestamp (seconds).
_MAX_SKEW = 300


@dataclass
class DevicePrincipal:
    device_id: uuid.UUID
    organization_id: uuid.UUID
    employee_id: uuid.UUID


async def get_device_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
) -> DevicePrincipal:
    try:
        payload = decode_token_of_type(creds.credentials, DEVICE)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=f"invalid device token: {exc}") from exc

    device_id = payload.get("sub")
    org_id = payload.get("org")
    emp_id = payload.get("emp")
    if not (device_id and org_id and emp_id):
        raise HTTPException(status_code=401, detail="malformed device token")

    if x_signature is None or x_timestamp is None:
        raise HTTPException(status_code=401, detail="missing request signature")

    # Reject stale/future timestamps (replay protection).
    try:
        ts = int(x_timestamp)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid timestamp")
    if abs(time.time() - ts) > _MAX_SKEW:
        raise HTTPException(status_code=401, detail="signature timestamp out of range")

    body_bytes = await request.body()
    body = body_bytes.decode("utf-8") if body_bytes else ""

    async with open_tenant_session(str(org_id)) as session:
        device = (
            await session.execute(select(Device).where(Device.id == uuid.UUID(device_id)))
        ).scalar_one_or_none()
        if device is None or device.status != "approved" or not device.signing_secret:
            raise HTTPException(status_code=403, detail="device not authorized")
        if not verify_signature(
            device.signing_secret, request.method, request.url.path, body, x_timestamp, x_signature
        ):
            raise HTTPException(status_code=401, detail="bad signature")

    return DevicePrincipal(
        device_id=uuid.UUID(device_id),
        organization_id=uuid.UUID(org_id),
        employee_id=uuid.UUID(emp_id),
    )
