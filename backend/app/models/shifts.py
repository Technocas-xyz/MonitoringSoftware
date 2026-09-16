from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import GUID, JSONB

# Shift states (see docs/04-shift-state-machine.md)
SCHEDULED = "SCHEDULED"
AVAILABLE = "AVAILABLE"
WORKING = "WORKING"
ON_BREAK = "ON_BREAK"
PAUSED = "PAUSED"
COMPLETED = "COMPLETED"
AUTO_COMPLETED = "AUTO_COMPLETED"
MISSED = "MISSED"
FORCE_STOPPED = "FORCE_STOPPED"
CANCELLED = "CANCELLED"

ACTIVE_STATES = (AVAILABLE, WORKING, ON_BREAK, PAUSED)
TERMINAL_STATES = (COMPLETED, AUTO_COMPLETED, MISSED, FORCE_STOPPED, CANCELLED)


class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"
    __table_args__ = (
        Index("ix_shifts_emp_start", "organization_id", "employee_id", "scheduled_start"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("work_schedules.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    schedule_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # optimistic-lock counter for transition conflict detection
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ShiftEvent(Base):
    __tablename__ = "shift_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_key", name="uq_shift_event_key"),
        Index("ix_shift_events_shift", "shift_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # employee|system|manager
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)


class Break(Base):
    __tablename__ = "breaks"
    __table_args__ = (Index("ix_breaks_shift", "shift_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exceeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "work_date", name="uq_attendance_day"),
        Index("ix_attendance_org_date", "organization_id", "work_date"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    scheduled_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    break_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    late_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    early_leave_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
