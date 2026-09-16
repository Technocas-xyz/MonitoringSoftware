"""Server time authority.

Per spec 15 and 100, the server is the sole authority for "now". All attendance,
lateness, overtime, and break calculations use this, never the client clock. Client
timestamps are advisory only. Everything is UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    """Authoritative current UTC time."""
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Normalize any aware/naive datetime to UTC (assume UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
