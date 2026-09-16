"""Auth routes: login, 2FA, refresh, logout, me."""
from __future__ import annotations

import uuid

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.auth.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenPair,
    TwoFARequiredResponse,
    TwoFAVerifyRequest,
)
from app.auth.service import authenticate, build_principal
from app.core.db import get_session, get_sessionmaker
from app.core.deps import get_principal
from app.core.security import (
    REFRESH,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token_of_type,
)
from app.core.tenant import set_current_org
from app.core.time_authority import now
from app.models.identity import User
from app.models.organization import Organization

router = APIRouter(prefix="/auth", tags=["auth"])


async def _resolve_org(session: AsyncSession, slug: str) -> Organization:
    org = (
        await session.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none()
    if org is None or org.status != "active":
        raise HTTPException(status_code=401, detail="invalid credentials")
    return org


@router.post("/login", responses={200: {"model": TokenPair}})
async def login(payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    org = await _resolve_org(session, payload.organization_slug)
    await set_current_org(session, str(org.id))
    user = await authenticate(session, org.id, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    if user.twofa_enabled:
        # Issue a short-lived challenge token; real tokens come after 2FA verify.
        challenge = create_access_token(str(user.id), str(org.id), stage="2fa")
        return TwoFARequiredResponse(challenge_token=challenge)

    user.last_login_at = now()
    await audit.record(
        session,
        action="auth.login",
        organization_id=org.id,
        actor_user_id=user.id,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return TokenPair(
        access_token=create_access_token(str(user.id), str(org.id)),
        refresh_token=create_refresh_token(str(user.id), str(org.id)),
    )


@router.post("/2fa/verify", response_model=TokenPair)
async def verify_2fa(payload: TwoFAVerifyRequest, session: AsyncSession = Depends(get_session)):
    try:
        claims = decode_token_of_type(payload.challenge_token, "access")
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="invalid challenge") from exc
    if claims.get("stage") != "2fa":
        raise HTTPException(status_code=401, detail="invalid challenge")

    org_id = uuid.UUID(claims["org"])
    await set_current_org(session, str(org_id))
    user = (
        await session.execute(select(User).where(User.id == uuid.UUID(claims["sub"])))
    ).scalar_one_or_none()
    if user is None or not user.twofa_secret:
        raise HTTPException(status_code=401, detail="invalid challenge")

    if not pyotp.TOTP(user.twofa_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=401, detail="invalid 2fa code")

    user.last_login_at = now()
    await audit.record(session, action="auth.login.2fa", organization_id=org_id, actor_user_id=user.id)
    await session.commit()
    return TokenPair(
        access_token=create_access_token(str(user.id), str(org_id)),
        refresh_token=create_refresh_token(str(user.id), str(org_id)),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest):
    try:
        claims = decode_token_of_type(payload.refresh_token, REFRESH)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    sub, org = claims["sub"], claims["org"]
    # Rotate: issue a fresh pair.
    return TokenPair(
        access_token=create_access_token(sub, org),
        refresh_token=create_refresh_token(sub, org),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(principal: Principal = Depends(get_principal)):
    # Stateless JWT: client discards tokens. A production build revokes the refresh jti in Redis.
    async with get_sessionmaker()() as session:
        await set_current_org(session, str(principal.organization_id))
        await audit.record(
            session,
            action="auth.logout",
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
        )
        await session.commit()


@router.get("/me", response_model=MeResponse)
async def me(principal: Principal = Depends(get_principal)):
    return MeResponse(
        user_id=principal.user_id,
        organization_id=principal.organization_id,
        email=principal.email,
        permissions=sorted(principal.permissions),
        roles=[r.role_key for r in principal.roles],
    )
