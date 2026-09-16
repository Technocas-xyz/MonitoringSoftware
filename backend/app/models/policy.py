from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import GUID


class ShiftPolicy(Base, TimestampMixin):
    __tablename__ = "shift_policies"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(32), default="hybrid", nullable=False)
    earliest_clock_in_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_clock_in_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    late_threshold_min: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    allow_break: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_break_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allow_multiple_breaks: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_early_clockout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_overtime: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    overtime_requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_end: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monitoring_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MonitoringPolicy(Base, TimestampMixin):
    __tablename__ = "monitoring_policies"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    monitor_applications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monitor_websites: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    website_mode: Mapped[str] = mapped_column(String(16), default="domain", nullable=False)
    monitor_idle: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    idle_threshold_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    idle_classification: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    monitor_kbd_mouse: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    screenshot_mode: Mapped[str] = mapped_column(String(16), default="off", nullable=False)
    screenshot_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    screenshot_capture_scope: Mapped[str] = mapped_column(
        String(16), default="working_only", nullable=False
    )
    screenshot_watermark: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PolicyAssignment(Base):
    __tablename__ = "policy_assignments"
    __table_args__ = (
        Index("ix_policy_assign", "organization_id", "policy_kind", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # shift|monitoring
    policy_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # organization|department|team|employee
    target_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    allow_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
