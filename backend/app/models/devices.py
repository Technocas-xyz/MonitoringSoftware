from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import GUID


class Device(Base, TimestampMixin):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_employee", "organization_id", "employee_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os: Mapped[str | None] = mapped_column(String(32), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # HMAC secret for signing agent requests; issued at enrollment, returned once.
    signing_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tracking_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
