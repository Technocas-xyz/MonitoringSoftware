from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import uuid_pk
from app.models.types import GUID, JSONB


class PayrollRun(Base):
    """A payroll run over a period (spec 77). Payroll rules are configurable per org and not
    tied to any single country's law. Access is restricted (payroll.run / rate.view)."""

    __tablename__ = "payroll_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft|finalized
    rules_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PayrollLine(Base):
    __tablename__ = "payroll_lines"
    __table_args__ = (Index("ix_payroll_line_run", "organization_id", "run_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    line_type: Mapped[str] = mapped_column(String(16), nullable=False)  # regular|overtime|leave|unpaid|adjustment
    hours: Mapped[float] = mapped_column(Numeric(8, 2), default=0, nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
