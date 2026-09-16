from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time_authority import now
from app.models.mixins import uuid_pk
from app.models.types import GUID, INET, JSONB


class AuditLog(Base):
    """Append-only audit trail (spec 46).

    No update/delete is exposed through the application. In production this table is
    partitioned by `at`; the initial migration creates the base table.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_at", "organization_id", "at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now(), nullable=False
    )
