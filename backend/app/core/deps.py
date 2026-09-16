"""FastAPI dependencies: authentication, tenant-scoped session, permission checks.

Flow for a tenant-scoped request:
  1. Decode the bearer access token -> user_id + org.
  2. Open a session and SET app.current_org (RLS now active).
  3. Load the user and build the Principal (permissions + scope).
  4. Route-level require_permission(...) enforces authorization.

Client-side authorization is never trusted; every gate here runs server-side (spec 100).
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.auth.service import build_principal
from app.core.security import ACCESS, TokenError, decode_token_of_type
from app.core.tenant import open_tenant_session
from app.models.identity import User

_bearer = HTTPBearer(auto_error=True)


async def get_token_payload(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    try:
        return decode_token_of_type(creds.credentials, ACCESS)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}"
        ) from exc


async def get_tenant_session(
    payload: dict = Depends(get_token_payload),
) -> AsyncGenerator[AsyncSession, None]:
    org_id = payload.get("org")
    if not org_id:
        raise HTTPException(status_code=401, detail="token missing organization")
    async with open_tenant_session(org_id) as session:
        yield session


async def get_principal(
    payload: dict = Depends(get_token_payload),
    session: AsyncSession = Depends(get_tenant_session),
) -> Principal:
    user_id = payload.get("sub")
    org_id = payload.get("org")
    result = await session.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.organization_id == uuid.UUID(org_id))
    )
    user = result.scalar_one_or_none()
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="user not found or inactive")
    return await build_principal(session, user)


def require_permission(permission: str):
    """Dependency factory enforcing a permission on the principal."""

    async def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {permission}",
            )
        return principal

    return _checker
