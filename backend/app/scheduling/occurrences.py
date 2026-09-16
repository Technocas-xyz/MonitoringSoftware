"""Compute concrete shift windows from a schedule definition for a given date.

A schedule "occurrence" is a (scheduled_start, scheduled_end) pair in UTC, derived from the
schedule definition applied to a local date in the effective timezone. All storage/return
values are timezone-aware UTC (spec 15/72). DST is handled by zoneinfo.

Supported definition shapes (see docs/02 work_schedules.definition):
  fixed:    {"days": {"mon": ["09:00","18:00"], ...}}
  flexible: {"required_seconds": 28800, "window": ["07:00","20:00"]}
  rotating: {"cycle_weeks": 2, "anchor": "2026-01-05", "weeks": [ {days...}, {days...} ]}
  multiple: {"days": {"mon": [["08:00","12:00"], ["14:00","18:00"]]}}  (fixed with lists)
  custom:   {"dates": {"2026-09-14": ["09:00","18:00"]}}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@dataclass
class Occurrence:
    scheduled_start: datetime  # UTC aware
    scheduled_end: datetime    # UTC aware


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def _local_dt(day: date, hhmm: str, tz: ZoneInfo) -> datetime:
    t = _parse_hhmm(hhmm)
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=tz)


def _to_utc(dt: datetime) -> datetime:
    return dt.astimezone(ZoneInfo("UTC"))


def _windows_for_day(day_def) -> list[tuple[str, str]]:
    """Normalize a day's definition into a list of (start, end) hhmm tuples."""
    if not day_def:
        return []
    # Either ["09:00","18:00"] or [["08:00","12:00"],["14:00","18:00"]]
    if isinstance(day_def[0], (list, tuple)):
        return [(w[0], w[1]) for w in day_def]
    return [(day_def[0], day_def[1])]


def compute_occurrences(
    schedule_type: str, definition: dict, day: date, tz_name: str
) -> list[Occurrence]:
    tz = ZoneInfo(tz_name)
    occ: list[Occurrence] = []

    if schedule_type == "fixed":
        wd = _WEEKDAYS[day.weekday()]
        for start, end in _windows_for_day(definition.get("days", {}).get(wd)):
            occ.append(_make(day, start, end, tz))

    elif schedule_type == "custom":
        key = day.isoformat()
        day_def = definition.get("dates", {}).get(key)
        for start, end in _windows_for_day(day_def):
            occ.append(_make(day, start, end, tz))

    elif schedule_type == "rotating":
        weeks = definition.get("weeks", [])
        cycle = definition.get("cycle_weeks", len(weeks) or 1)
        anchor_str = definition.get("anchor")
        if weeks and anchor_str:
            anchor = date.fromisoformat(anchor_str)
            weeks_elapsed = (day - anchor).days // 7
            idx = weeks_elapsed % cycle
            week_def = weeks[idx] if idx < len(weeks) else {}
            wd = _WEEKDAYS[day.weekday()]
            for start, end in _windows_for_day(week_def.get("days", {}).get(wd)):
                occ.append(_make(day, start, end, tz))

    elif schedule_type == "flexible":
        window = definition.get("window")
        if window:
            occ.append(_make(day, window[0], window[1], tz))

    return occ


def _make(day: date, start: str, end: str, tz: ZoneInfo) -> Occurrence:
    start_local = _local_dt(day, start, tz)
    end_local = _local_dt(day, end, tz)
    # Overnight shift: end <= start means it rolls into the next day.
    if end_local <= start_local:
        end_local = end_local + timedelta(days=1)
    return Occurrence(scheduled_start=_to_utc(start_local), scheduled_end=_to_utc(end_local))
