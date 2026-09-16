from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceEnrollRequest(BaseModel):
    employee_id: uuid.UUID
    hostname: str | None = None
    os: str | None = None
    os_version: str | None = None
    agent_version: str | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    hostname: str | None
    os: str | None
    agent_version: str | None
    status: str
    last_seen_at: datetime | None
    approved_at: datetime | None
    revoked_at: datetime | None


class DeviceApproveOut(DeviceOut):
    # signing_secret is returned exactly once, on approval.
    signing_secret: str | None = None
