"""Baseline default policies.

When no policy is assigned at any level, these documented defaults apply. They match
docs/07 and doc 00 A6 (idle default = idle). Never hard-coded per employee; they are the
system fallback only.
"""
from __future__ import annotations

DEFAULT_SHIFT_POLICY: dict = {
    "tracking_mode": "hybrid",
    "earliest_clock_in_min": 15,
    "latest_clock_in_min": 30,
    "late_threshold_min": 15,
    "allow_break": True,
    "max_break_seconds": 3600,
    "allow_multiple_breaks": True,
    "allow_early_clockout": False,
    "allow_overtime": True,
    "overtime_requires_approval": True,
    "auto_start": False,
    "auto_end": True,
    "monitoring_required": True,
}

DEFAULT_MONITORING_POLICY: dict = {
    "monitor_applications": True,
    "monitor_websites": True,
    "website_mode": "domain",
    "monitor_idle": True,
    "idle_threshold_seconds": 600,
    "idle_classification": "idle",
    "monitor_kbd_mouse": True,
    "screenshot_mode": "off",
    "screenshot_interval_seconds": None,
    "screenshot_capture_scope": "working_only",
    "screenshot_watermark": False,
}

SHIFT_FIELDS = list(DEFAULT_SHIFT_POLICY.keys())
MONITORING_FIELDS = list(DEFAULT_MONITORING_POLICY.keys())
