from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ShiftCreateRequest(BaseModel):
    employee_id: uuid.UUID
    day: date


class ShiftActionRequest(BaseModel):
    device_id: uuid.UUID | None = None
    client_time: datetime | None = None
    event_id: str | None = None
    is_break: bool = True  # used by pause: break vs non-break pause


class ForceStopRequest(BaseModel):
    reason: str
    event_id: str | None = None


class ShiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: uuid.UUID
    state: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    timezone: str
    version: int


class ShiftEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    occurred_at: datetime
    source: str
