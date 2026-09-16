"""Screenshot retention sweep (spec 25/82). Deletes expired blobs + metadata, audits each."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core.time_authority import now
from app.models.monitoring import Screenshot
from app.screenshots.storage import get_storage_provider


async def purge_expired_screenshots(session: AsyncSession, org_id: uuid.UUID) -> int:
    provider = get_storage_provider()
    server_now = now()
    expired = (
        await session.execute(
            select(Screenshot).where(
                Screenshot.organization_id == org_id,
                Screenshot.retention_until.is_not(None),
                Screenshot.retention_until < server_now,
            )
        )
    ).scalars().all()

    count = 0
    for shot in expired:
        try:
            provider.delete(shot.storage_key)
        except Exception:
            # Best-effort blob delete; metadata removal + audit still proceed.
            pass
        await audit.record(
            session, action="screenshot.retention_delete", organization_id=org_id,
            target_type="screenshot", target_id=shot.id,
            old_value={"captured_at": shot.captured_at.isoformat()},
        )
        await session.delete(shot)
        count += 1
    await session.flush()
    return count
