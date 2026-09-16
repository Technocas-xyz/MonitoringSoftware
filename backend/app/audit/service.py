"""Append-only audit writer (spec 46).

The only supported way to write audit records. There is deliberately no update/delete path.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def record(
    session: AsyncSession,
    *,
    action: str,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    ip: str | None = None,
    device_id: uuid.UUID | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        id=uuid.uuid4(),
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=ip,
        device_id=device_id,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )
    session.add(entry)
    await session.flush()
    return entry
