from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time_authority import now
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import GUID, JSONB


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)


class TaskTimeEntry(Base):
    __tablename__ = "task_time_entries"
    __table_args__ = (Index("ix_tte_emp", "organization_id", "employee_id", "started_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    shift_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)  # agent|manual


class Timesheet(Base):
    __tablename__ = "timesheets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "employee_id", "period_start", "period_end", name="uq_timesheet_period"
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    # draft|submitted|approved|rejected|locked
    approved_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timesheet_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    break_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overtime_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)


class TimesheetCorrection(Base):
    __tablename__ = "timesheet_corrections"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timesheet_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("timesheets.id", ondelete="SET NULL"), nullable=True
    )
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("timesheet_entries.id", ondelete="SET NULL"), nullable=True
    )
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # missed_clockin|incorrect_clockout|incorrect_break|wrong_project|wrong_task
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now(), nullable=False
    )
