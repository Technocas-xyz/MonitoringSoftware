"""SSO authorize + callback (spec 79).

The callback resolves an org (by slug), exchanges the code for a verified identity via the
configured provider, then links the identity to an existing user (by sso_subject or email) or
provisions a new one, and issues platform tokens. SSO must be enabled in the org settings.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.schemas import TokenPair
from app.core.db import get_session
from app.core.security import create_access_token, create_refresh_token
from app.core.tenant import set_current_org
from app.core.time_authority import now
from app.models.identity import User
from app.models.organization import Organization
from app.sso.provider import get_provider

router = APIRouter(prefix="/auth/sso", tags=["sso"])


class AuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class CallbackRequest(BaseModel):
    organization_slug: str
    provider: str
    code: str
    redirect_uri: str = "https://app.local/sso/callback"


async def _org(session: AsyncSession, slug: str) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if org is None or org.status != "active":
        raise HTTPException(status_code=404, detail="organization not found")
    return org


def _sso_enabled(org: Organization, provider_key: str) -> bool:
    sso = (org.settings or {}).get("sso", {})
    return bool(sso.get("enabled")) and provider_key in (sso.get("providers", []) or [])


@router.get("/{provider}/authorize", response_model=AuthorizeResponse)
async def authorize(
    provider: str,
    organization_slug: str,
    redirect_uri: str = "https://app.local/sso/callback",
    session: AsyncSession = Depends(get_session),
):
    org = await _org(session, organization_slug)
    if not _sso_enabled(org, provider):
        raise HTTPException(status_code=400, detail="SSO provider not enabled for this organization")
    prov = get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="unknown SSO provider")
    state = uuid.uuid4().hex
    return AuthorizeResponse(authorize_url=prov.authorize_url(state, redirect_uri), state=state)


@router.post("/{provider}/callback", response_model=TokenPair)
async def callback(
    provider: str,
    payload: CallbackRequest,
    session: AsyncSession = Depends(get_session),
):
    org = await _org(session, payload.organization_slug)
    if not _sso_enabled(org, provider):
        raise HTTPException(status_code=400, detail="SSO provider not enabled for this organization")
    prov = get_provider(provider)
    if prov is None:
        raise HTTPException(status_code=404, detail="unknown SSO provider")

    identity = await prov.exchange(payload.code, payload.redirect_uri)
    await set_current_org(session, str(org.id))

    # Link by sso_subject, then by email; otherwise provision a new SSO user.
    user = (
        await session.execute(
            select(User).where(User.organization_id == org.id, User.sso_subject == identity.subject)
        )
    ).scalar_one_or_none()
    if user is None:
        user = (
            await session.execute(
                select(User).where(User.organization_id == org.id, User.email == identity.email)
            )
        ).scalar_one_or_none()
        if user is not None:
            user.sso_subject = identity.subject  # link existing account
        else:
            user = User(
                id=uuid.uuid4(), organization_id=org.id, email=identity.email,
                full_name=identity.full_name or identity.email, sso_subject=identity.subject,
                password_hash=None,  # SSO-only account
            )
            session.add(user)
            await session.flush()

    if user.status != "active":
        raise HTTPException(status_code=403, detail="user is disabled")

    user.last_login_at = now()
    await audit.record(
        session, action="auth.sso.login", organization_id=org.id, actor_user_id=user.id,
        new_value={"provider": provider, "subject": identity.subject},
    )
    await session.commit()
    return TokenPair(
        access_token=create_access_token(str(user.id), str(org.id)),
        refresh_token=create_refresh_token(str(user.id), str(org.id)),
    )
