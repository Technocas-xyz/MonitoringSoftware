from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import uuid_pk
from app.models.types import GUID


class OfficeLocation(Base):
    """A named geofenced location (spec 75). Optional module; only used when geolocation is
    explicitly enabled in org settings."""

    __tablename__ = "office_locations"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[int] = mapped_column(Integer, default=150, nullable=False)


class GeofenceEvent(Base):
    """A location ping with its geofence evaluation (inside/outside). Latitude/longitude are
    stored only when geolocation is enabled; this is privacy-sensitive and opt-in (spec 75)."""

    __tablename__ = "geofence_events"
    __table_args__ = (Index("ix_geofence_emp", "organization_id", "employee_id", "occurred_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    inside: Mapped[bool] = mapped_column(Boolean, nullable=False)
    distance_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
