"""High-volume monitoring event models (docs/02 §7).

Production note: on PostgreSQL these tables are declared PARTITION BY RANGE (occurred_at)
(monthly) with a composite PK (id, occurred_at); the base migration creates them and a beat
job pre-creates partitions. For portability (and SQLite-based unit tests) the ORM models use a
single-column UUID PK plus an indexed occurred_at; the partitioning is applied at the DDL
level in production and does not change the query surface used here.

Idempotency: every table has a UNIQUE (organization_id, event_key) so re-sent batches from
the agent's offline queue never double-insert (spec 19/52).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import uuid_pk
from app.models.types import GUID


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_appevent_key"),
        Index("ix_appev_emp", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    application: Mapped[str] = mapped_column(String(255), nullable=False)
    process_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    window_title: Mapped[str | None] = mapped_column(String(512), nullable=True)  # dropped if policy forbids
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)


class WebsiteEvent(Base):
    __tablename__ = "website_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_webevent_key"),
        Index("ix_webev_emp", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # only if website_mode=full_url
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)


class ActivityInterval(Base):
    __tablename__ = "activity_intervals"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_actint_key"),
        Index("ix_actint_emp", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    keyboard_pct: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    mouse_pct: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    combined_pct: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_idle: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)


class Screenshot(Base):
    __tablename__ = "screenshots"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_screenshot_key"),
        Index("ix_shots_emp", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    shift_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    thumb_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watermarked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encryption_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|stored
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)


class ScreenshotAccessLog(Base):
    __tablename__ = "screenshot_access_log"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    screenshot_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # view|download
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
