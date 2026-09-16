"""Security primitives: password hashing and JWT token creation/verification.

Spec 45: password hashing, token expiration, session management. Access tokens are
short-lived; refresh tokens rotate. Authorization decisions are always made server-side.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.time_authority import now

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS = "access"
REFRESH = "refresh"
DEVICE = "device"


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return _pwd.verify(raw, hashed)


def _create_token(subject: str, token_type: str, expires: timedelta, claims: dict[str, Any]) -> str:
    issued = now()
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(issued.timestamp()),
        "exp": int((issued + expires).timestamp()),
        "jti": str(uuid.uuid4()),
        **claims,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, organization_id: str, **claims: Any) -> str:
    return _create_token(
        subject,
        ACCESS,
        timedelta(minutes=settings.access_token_expire_minutes),
        {"org": organization_id, **claims},
    )


def create_refresh_token(subject: str, organization_id: str) -> str:
    return _create_token(
        subject,
        REFRESH,
        timedelta(days=settings.refresh_token_expire_days),
        {"org": organization_id},
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])


class TokenError(Exception):
    pass


def decode_token_of_type(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = decode_token(token)
    except JWTError as exc:  # pragma: no cover - passthrough
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError("unexpected token type")
    return payload


def create_device_token(device_id: str, organization_id: str, employee_id: str) -> str:
    """Long-lived-ish device token (still bounded). Refreshed by the agent as needed."""
    from datetime import timedelta

    return _create_token(
        device_id,
        DEVICE,
        timedelta(days=settings.refresh_token_expire_days),
        {"org": organization_id, "emp": employee_id},
    )


def new_signing_secret() -> str:
    """Generate a device HMAC signing secret (returned once at enrollment/approval)."""
    return secrets.token_hex(32)


def sign_request(secret: str, method: str, path: str, body: str, timestamp: str) -> str:
    """Compute the HMAC-SHA256 signature the agent must send (spec 45/60).

    Canonical string: METHOD\\nPATH\\nTIMESTAMP\\nSHA256(body-hex). The agent and server compute
    this identically; the server rejects mismatches and stale timestamps.
    """
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{body_hash}"
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(
    secret: str, method: str, path: str, body: str, timestamp: str, provided: str
) -> bool:
    expected = sign_request(secret, method, path, body, timestamp)
    return hmac.compare_digest(expected, provided)
