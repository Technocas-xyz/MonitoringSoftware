"""Screenshot retention resolution (spec 25/82).

Retention days are read from organization.settings.retention.screenshots (never hard-coded).
A sensible default applies when unset. The retention worker deletes expired screenshots and
records an audit entry for each deletion.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_authority import now
from app.models.organization import Organization

DEFAULT_SCREENSHOT_RETENTION_DAYS = 30


async def screenshot_retention_days(session: AsyncSession, org_id: uuid.UUID) -> int:
    org = (
        await session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        return DEFAULT_SCREENSHOT_RETENTION_DAYS
    retention = (org.settings or {}).get("retention", {})
    return int(retention.get("screenshots", DEFAULT_SCREENSHOT_RETENTION_DAYS))


async def compute_retention_until(session: AsyncSession, org_id: uuid.UUID):
    days = await screenshot_retention_days(session, org_id)
    return now() + timedelta(days=days)
