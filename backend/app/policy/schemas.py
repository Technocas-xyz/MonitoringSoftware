from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class ShiftPolicyCreate(BaseModel):
    name: str
    tracking_mode: str = "hybrid"
    earliest_clock_in_min: int | None = 15
    latest_clock_in_min: int | None = 30
    late_threshold_min: int = 15
    allow_break: bool = True
    max_break_seconds: int | None = 3600
    allow_multiple_breaks: bool = True
    allow_early_clockout: bool = False
    allow_overtime: bool = True
    overtime_requires_approval: bool = True
    auto_start: bool = False
    auto_end: bool = True
    monitoring_required: bool = True


class ShiftPolicyOut(ShiftPolicyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class MonitoringPolicyCreate(BaseModel):
    name: str
    monitor_applications: bool = True
    monitor_websites: bool = True
    website_mode: str = "domain"
    monitor_idle: bool = True
    idle_threshold_seconds: int = 600
    idle_classification: str = "idle"
    monitor_kbd_mouse: bool = True
    screenshot_mode: str = "off"
    screenshot_interval_seconds: int | None = None
    screenshot_capture_scope: str = "working_only"
    screenshot_watermark: bool = False


class MonitoringPolicyOut(MonitoringPolicyCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class PolicyAssignRequest(BaseModel):
    policy_kind: str  # shift|monitoring
    policy_id: uuid.UUID
    target_type: str  # organization|department|team|employee
    target_id: uuid.UUID
    allow_override: bool = False
    priority: int = 0


class PolicyPreviewResponse(BaseModel):
    employee_id: uuid.UUID
    shift: dict
    monitoring: dict
    summary: list[str]
