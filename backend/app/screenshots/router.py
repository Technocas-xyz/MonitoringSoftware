"""Screenshot API (spec 24/25/86, doc 03 §8).

Agent (device-auth):
  POST /screenshots/presign   -> register metadata (pending) + presigned PUT url
  POST /screenshots/{id}/confirm -> mark stored + set retention_until

Viewers (user-auth):
  GET  /screenshots            -> list (screenshot.view), scope-narrowed
  GET  /screenshots/{id}/url   -> short-lived signed GET url; LOGS the access (view/download)

Every view/download is written to screenshot_access_log (spec 86).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.deps import DevicePrincipal, get_device_principal
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.core.tenant import open_tenant_session
from app.core.time_authority import now
from app.models.monitoring import Screenshot, ScreenshotAccessLog
from app.screenshots.retention import compute_retention_until
from app.screenshots.storage import get_storage_provider

router = APIRouter(prefix="/screenshots", tags=["screenshots"])


class PresignRequest(BaseModel):
    captured_at: datetime
    bytes: int | None = None
    shift_id: uuid.UUID | None = None
    event_id: str


class PresignResponse(BaseModel):
    screenshot_id: uuid.UUID
    storage_key: str
    upload_url: str


class ScreenshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    shift_id: uuid.UUID | None
    captured_at: datetime
    status: str
    watermarked: bool


class SignedUrlOut(BaseModel):
    url: str
    expires_seconds: int


@router.post("/presign", response_model=PresignResponse)
async def presign(payload: PresignRequest, dp: DevicePrincipal = Depends(get_device_principal)):
    provider = get_storage_provider()
    async with open_tenant_session(str(dp.organization_id)) as session:
        # Idempotency: reuse existing metadata for the same event_id.
        existing = (
            await session.execute(
                select(Screenshot).where(
                    Screenshot.organization_id == dp.organization_id,
                    Screenshot.event_key == payload.event_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return PresignResponse(
                screenshot_id=existing.id,
                storage_key=existing.storage_key,
                upload_url=provider.presign_put(existing.storage_key),
            )

        sid = uuid.uuid4()
        storage_key = provider.key_for(dp.organization_id, sid)
        shot = Screenshot(
            id=sid, organization_id=dp.organization_id, employee_id=dp.employee_id,
            device_id=dp.device_id, shift_id=payload.shift_id,
            storage_key=storage_key, captured_at=payload.captured_at, bytes=payload.bytes,
            status="pending", occurred_at=payload.captured_at, event_key=payload.event_id,
        )
        session.add(shot)
        await session.commit()
        return PresignResponse(
            screenshot_id=sid, storage_key=storage_key,
            upload_url=provider.presign_put(storage_key),
        )


@router.post("/{screenshot_id}/confirm", response_model=ScreenshotOut)
async def confirm(screenshot_id: uuid.UUID, dp: DevicePrincipal = Depends(get_device_principal)):
    async with open_tenant_session(str(dp.organization_id)) as session:
        shot = (
            await session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
        ).scalar_one_or_none()
        if shot is None or shot.device_id != dp.device_id:
            raise HTTPException(status_code=404, detail="screenshot not found")
        shot.status = "stored"
        shot.retention_until = await compute_retention_until(session, dp.organization_id)
        await session.commit()
        return ScreenshotOut.model_validate(shot)


@router.get("", response_model=list[ScreenshotOut])
async def list_screenshots(
    employee_id: uuid.UUID | None = None,
    principal: Principal = Depends(require_permission("screenshot.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    stmt = select(Screenshot).where(Screenshot.status == "stored")
    if employee_id:
        stmt = stmt.where(Screenshot.employee_id == employee_id)
    stmt = stmt.order_by(Screenshot.captured_at.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()
    return [ScreenshotOut.model_validate(r) for r in rows]


@router.get("/{screenshot_id}/url", response_model=SignedUrlOut)
async def get_signed_url(
    screenshot_id: uuid.UUID,
    request: Request,
    download: bool = False,
    principal: Principal = Depends(require_permission("screenshot.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if download and not principal.has("screenshot.download"):
        raise HTTPException(status_code=403, detail="missing permission: screenshot.download")

    shot = (
        await session.execute(select(Screenshot).where(Screenshot.id == screenshot_id))
    ).scalar_one_or_none()
    if shot is None or shot.status != "stored":
        raise HTTPException(status_code=404, detail="screenshot not found")

    provider = get_storage_provider()
    url = provider.presign_get(shot.storage_key, expires_seconds=300)

    # Log every view/download (spec 86).
    session.add(ScreenshotAccessLog(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        screenshot_id=shot.id, actor_user_id=principal.user_id,
        action="download" if download else "view", at=now(),
        ip=request.client.host if request.client else None,
    ))
    await session.commit()
    return SignedUrlOut(url=url, expires_seconds=300)
