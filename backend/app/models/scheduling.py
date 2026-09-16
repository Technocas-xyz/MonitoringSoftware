from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import GUID, JSONB


class WorkSchedule(Base, TimestampMixin):
    __tablename__ = "work_schedules"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # fixed|flexible|rotating|custom
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ScheduleAssignment(Base):
    __tablename__ = "schedule_assignments"
    __table_args__ = (
        Index("ix_sched_assign_target", "organization_id", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("work_schedules.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)  # employee|team|department
    target_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class HolidayCalendar(Base):
    __tablename__ = "holiday_calendars"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HolidayDay(Base):
    __tablename__ = "holiday_days"
    __table_args__ = (Index("ix_holiday_cal_day", "calendar_id", "day", unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    calendar_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("holiday_calendars.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"
    __table_args__ = (Index("ix_leave_emp", "organization_id", "employee_id", "start_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # annual|sick|casual|custom
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    approver_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
