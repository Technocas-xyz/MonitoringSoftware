from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins import uuid_pk
from app.models.types import GUID, JSONB


class AIJob(Base):
    """A record of an AI request (spec 47). `scope` is a snapshot of the caller's RBAC scope so
    the job's data access can be reproduced and audited; AI never reads outside it (spec 90)."""

    __tablename__ = "ai_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # summary|anomaly|nl_query
    scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
