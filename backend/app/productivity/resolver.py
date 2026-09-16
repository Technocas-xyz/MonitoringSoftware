"""Classification resolution + productivity indicator (spec 26/27).

Classification is scoped: the same app/domain can be productive for one department and
unproductive for another (spec 26). Resolution specificity: team > department > organization.
Unclassified apps/domains fall back to neutral.

The indicator is a configurable weighted ratio over classified time:

    indicator = 100 * (Σ seconds_c * weight_c) / (Σ seconds_c)

where weight_c comes from the productivity category (default productive=1, neutral=0.5,
unproductive=0). Idle time is excluded from the denominator here; dashboards report it
separately. This is an *indicator*, not an absolute measure of performance.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.productivity import (
    ApplicationClassification,
    ProductivityCategory,
    WebsiteClassification,
)
from app.productivity.defaults import NEUTRAL

_SPECIFICITY = {"team": 3, "department": 2, "organization": 1}


@dataclass
class CategoryWeights:
    # category key -> weight
    weights: dict[str, float]

    def weight_for(self, key: str) -> float:
        return self.weights.get(key, 0.5)


async def load_category_weights(session: AsyncSession, org_id: uuid.UUID) -> CategoryWeights:
    rows = (
        await session.execute(
            select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id)
        )
    ).scalars().all()
    weights = {r.key: float(r.weight) for r in rows}
    # id -> key map is convenient for classification lookups
    return CategoryWeights(weights=weights)


async def _category_key_by_id(session: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, str]:
    rows = (
        await session.execute(
            select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id)
        )
    ).scalars().all()
    return {r.id: r.key for r in rows}


def _pick(rows, team_id, department_id) -> uuid.UUID | None:
    """Choose the most specific matching classification's category_id."""
    best = None
    best_rank = -1
    for r in rows:
        if r.scope_type == "team" and r.scope_id != team_id:
            continue
        if r.scope_type == "department" and r.scope_id != department_id:
            continue
        if r.scope_type == "organization":
            pass  # always matches
        rank = _SPECIFICITY.get(r.scope_type, 0)
        if rank > best_rank:
            best_rank = rank
            best = r.category_id
    return best


async def classify_application(
    session: AsyncSession, org_id: uuid.UUID, application: str,
    team_id: uuid.UUID | None, department_id: uuid.UUID | None,
    id_to_key: dict[uuid.UUID, str],
) -> str:
    rows = (
        await session.execute(
            select(ApplicationClassification).where(
                ApplicationClassification.organization_id == org_id,
                ApplicationClassification.application == application,
            )
        )
    ).scalars().all()
    cat_id = _pick(rows, team_id, department_id)
    return id_to_key.get(cat_id, NEUTRAL) if cat_id else NEUTRAL


async def classify_website(
    session: AsyncSession, org_id: uuid.UUID, domain: str,
    team_id: uuid.UUID | None, department_id: uuid.UUID | None,
    id_to_key: dict[uuid.UUID, str],
) -> str:
    rows = (
        await session.execute(
            select(WebsiteClassification).where(
                WebsiteClassification.organization_id == org_id,
                WebsiteClassification.domain == domain,
            )
        )
    ).scalars().all()
    cat_id = _pick(rows, team_id, department_id)
    return id_to_key.get(cat_id, NEUTRAL) if cat_id else NEUTRAL


def compute_indicator(seconds_by_category: dict[str, int], weights: CategoryWeights) -> float:
    """Weighted-ratio indicator over classified seconds. Returns 0..100 rounded to 2dp."""
    total = sum(seconds_by_category.values())
    if total <= 0:
        return 0.0
    weighted = sum(sec * weights.weight_for(cat) for cat, sec in seconds_by_category.items())
    return round(100.0 * weighted / total, 2)
