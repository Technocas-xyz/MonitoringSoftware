"""Organization settings API (spec 61/82/83).

A single JSON settings blob per org holds retention, privacy toggles, SSO, geo, and payroll
configuration. GET is broadly viewable; PATCH requires settings.manage and deep-merges the
provided keys so callers can update one section at a time.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.models.organization import Organization

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    settings: dict


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


async def _org(session: AsyncSession, principal: Principal) -> Organization:
    return (
        await session.execute(
            select(Organization).where(Organization.id == principal.organization_id)
        )
    ).scalar_one()


@router.get("")
async def get_settings(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_tenant_session),
):
    org = await _org(session, principal)
    return {"settings": org.settings or {}}


@router.patch("")
async def patch_settings(
    payload: SettingsPatch,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    org = await _org(session, principal)
    old = dict(org.settings or {})
    org.settings = _deep_merge(old, payload.settings)
    await audit.record(
        session, action="settings.update", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="organization", target_id=org.id,
        old_value={"keys": list(old.keys())}, new_value={"keys": list(org.settings.keys())},
    )
    await session.commit()
    return {"settings": org.settings}
