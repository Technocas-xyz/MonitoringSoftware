"""Productivity category seeding + shared helpers."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.productivity import ProductivityCategory
from app.productivity.defaults import DEFAULT_CATEGORIES


async def ensure_default_categories(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Idempotently create the three default categories for an org if missing."""
    existing = {
        c.key
        for c in (
            await session.execute(
                select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id)
            )
        ).scalars().all()
    }
    for key, (label, weight) in DEFAULT_CATEGORIES.items():
        if key not in existing:
            session.add(ProductivityCategory(
                id=uuid.uuid4(), organization_id=org_id, key=key, label=label, weight=weight,
            ))
    await session.flush()


async def category_id_to_key(session: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        await session.execute(
            select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id)
        )
    ).scalars().all()
    return {r.id: r.key for r in rows}
