from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class WorkScheduleCreate(BaseModel):
    name: str
    type: str  # fixed|flexible|rotating|custom
    timezone: str | None = None
    definition: dict


class WorkScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    type: str
    timezone: str | None
    definition: dict


class ScheduleAssignRequest(BaseModel):
    schedule_id: uuid.UUID
    target_type: str  # employee|team|department
    target_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None
    priority: int = 0


class OccurrenceOut(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime


class OccurrencesResponse(BaseModel):
    employee_id: uuid.UUID
    day: date
    schedule_id: uuid.UUID | None
    timezone: str | None
    occurrences: list[OccurrenceOut]
