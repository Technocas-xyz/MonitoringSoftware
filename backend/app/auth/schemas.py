from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    organization_slug: str
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TwoFARequiredResponse(BaseModel):
    twofa_required: bool = True
    challenge_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TwoFAVerifyRequest(BaseModel):
    challenge_token: str
    code: str


class MeResponse(BaseModel):
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    permissions: list[str]
    roles: list[str]
