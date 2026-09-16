"""Productivity classification API (spec 26/27)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.models.productivity import (
    ApplicationClassification,
    ProductivityCategory,
    WebsiteClassification,
)
from app.productivity.service import ensure_default_categories

router = APIRouter(tags=["productivity"])


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    label: str
    weight: float


class CategoryUpsert(BaseModel):
    key: str
    label: str
    weight: float


class ClassificationCreate(BaseModel):
    target: str            # application name or domain
    category_key: str
    scope_type: str = "organization"  # organization|department|team
    scope_id: uuid.UUID | None = None


class ClassificationOut(BaseModel):
    id: uuid.UUID
    target: str
    category_key: str
    scope_type: str
    scope_id: uuid.UUID | None


@router.get("/productivity/categories", response_model=list[CategoryOut])
async def list_categories(
    principal: Principal = Depends(require_permission("analytics.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    await ensure_default_categories(session, principal.organization_id)
    await session.commit()
    rows = (
        await session.execute(
            select(ProductivityCategory).where(
                ProductivityCategory.organization_id == principal.organization_id
            )
        )
    ).scalars().all()
    return [CategoryOut.model_validate(r) for r in rows]


@router.put("/productivity/categories", response_model=CategoryOut)
async def upsert_category(
    payload: CategoryUpsert,
    principal: Principal = Depends(require_permission("productivity.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    cat = (
        await session.execute(
            select(ProductivityCategory).where(
                ProductivityCategory.organization_id == principal.organization_id,
                ProductivityCategory.key == payload.key,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        cat = ProductivityCategory(
            id=uuid.uuid4(), organization_id=principal.organization_id,
            key=payload.key, label=payload.label, weight=payload.weight,
        )
        session.add(cat)
    else:
        cat.label = payload.label
        cat.weight = payload.weight
    await audit.record(
        session, action="productivity.category.upsert", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="productivity_category", target_id=cat.id,
        new_value={"key": payload.key, "weight": payload.weight},
    )
    await session.commit()
    return CategoryOut.model_validate(cat)


async def _resolve_category(session, org_id, category_key) -> ProductivityCategory:
    await ensure_default_categories(session, org_id)
    cat = (
        await session.execute(
            select(ProductivityCategory).where(
                ProductivityCategory.organization_id == org_id,
                ProductivityCategory.key == category_key,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise HTTPException(status_code=422, detail=f"unknown category: {category_key}")
    return cat


@router.post("/applications/classifications", response_model=ClassificationOut, status_code=201)
async def classify_application(
    payload: ClassificationCreate,
    principal: Principal = Depends(require_permission("classification.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    cat = await _resolve_category(session, principal.organization_id, payload.category_key)
    row = ApplicationClassification(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        application=payload.target, category_id=cat.id,
        scope_type=payload.scope_type, scope_id=payload.scope_id,
    )
    session.add(row)
    await audit.record(
        session, action="classification.application", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="application_classification", target_id=row.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return ClassificationOut(
        id=row.id, target=row.application, category_key=payload.category_key,
        scope_type=row.scope_type, scope_id=row.scope_id,
    )


@router.post("/websites/classifications", response_model=ClassificationOut, status_code=201)
async def classify_website(
    payload: ClassificationCreate,
    principal: Principal = Depends(require_permission("classification.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    cat = await _resolve_category(session, principal.organization_id, payload.category_key)
    row = WebsiteClassification(
        id=uuid.uuid4(), organization_id=principal.organization_id,
        domain=payload.target, category_id=cat.id,
        scope_type=payload.scope_type, scope_id=payload.scope_id,
    )
    session.add(row)
    await audit.record(
        session, action="classification.website", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="website_classification", target_id=row.id,
        new_value=payload.model_dump(mode="json"),
    )
    await session.commit()
    return ClassificationOut(
        id=row.id, target=row.domain, category_key=payload.category_key,
        scope_type=row.scope_type, scope_id=row.scope_id,
    )
