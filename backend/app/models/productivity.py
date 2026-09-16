from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import uuid_pk
from app.models.types import GUID


class ProductivityCategory(Base):
    __tablename__ = "productivity_categories"
    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_prod_cat_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(32), nullable=False)  # productive|neutral|unproductive
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    # Weight used by the indicator formula (e.g. productive=1, neutral=0.5, unproductive=0).
    weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0, nullable=False)


class ApplicationClassification(Base):
    __tablename__ = "application_classifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "application", "scope_type", "scope_id", name="uq_appclass"
        ),
        Index("ix_appclass_org_app", "organization_id", "application"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("productivity_categories.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), default="organization", nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class WebsiteClassification(Base):
    __tablename__ = "website_classifications"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "domain", "scope_type", "scope_id", name="uq_webclass"
        ),
        Index("ix_webclass_org_domain", "organization_id", "domain"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("productivity_categories.id", ondelete="CASCADE"), nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(32), default="organization", nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class DailyEmployeeRollup(Base):
    __tablename__ = "daily_employee_rollup"

    organization_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tracked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    neutral_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unproductive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productivity_indicator: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)


class DailyTeamRollup(Base):
    __tablename__ = "daily_team_rollup"

    organization_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, primary_key=True)
    employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tracked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    neutral_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unproductive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productivity_indicator: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)


class DailyDepartmentRollup(Base):
    __tablename__ = "daily_department_rollup"

    organization_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    department_id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    work_date: Mapped[date] = mapped_column(Date, primary_key=True)
    employees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tracked_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    neutral_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unproductive_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    productivity_indicator: Mapped[float] = mapped_column(Numeric(5, 2), default=0, nullable=False)
