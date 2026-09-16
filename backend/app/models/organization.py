from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import TimestampMixin, uuid_pk
from app.models.types import JSONB


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
