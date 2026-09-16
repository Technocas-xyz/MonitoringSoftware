"""Attendance derivation (docs/04 §5, spec 8).

Attendance is a *derived* projection computed from the authoritative shift + shift_events +
breaks (spec 54). This module recomputes it from those records; it never invents time.

Durations in seconds. Times UTC. Status is derived from the computed durations and policy.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_authority import now, to_utc
from app.models.shifts import (
    AUTO_COMPLETED,
    CANCELLED,
    COMPLETED,
    FORCE_STOPPED,
    MISSED,
    Attendance,
    Break,
    Shift,
)

# Attendance statuses
PRESENT = "PRESENT"
LATE = "LATE"
ABSENT = "ABSENT"
PARTIAL = "PARTIAL"
EARLY_LEAVE = "EARLY_LEAVE"
OVERTIME = "OVERTIME"
ON_LEAVE = "ON_LEAVE"
HOLIDAY = "HOLIDAY"
REST_DAY = "REST_DAY"
MISSED_SHIFT = "MISSED_SHIFT"


@dataclass
class DerivedDurations:
    worked_seconds: int
    break_seconds: int
    idle_seconds: int
    late_seconds: int
    early_leave_seconds: int
    overtime_seconds: int


async def _sum_breaks(session: AsyncSession, shift_id: uuid.UUID) -> int:
    breaks = (
        await session.execute(select(Break).where(Break.shift_id == shift_id))
    ).scalars().all()
    total = 0
    for b in breaks:
        if b.ended_at is not None:
            total += int((to_utc(b.ended_at) - to_utc(b.started_at)).total_seconds())
    return total


async def _sum_idle(session: AsyncSession, shift_id: uuid.UUID) -> int:
    """Sum idle interval durations recorded by monitoring (Phase 4).

    Idle time is folded into attendance from activity_intervals flagged is_idle. Whether idle
    counts against working time is a policy choice (idle_classification); here we always report
    idle_seconds and subtract it from worked time only when the policy classifies idle as
    non-working (the default).
    """
    from app.models.monitoring import ActivityInterval

    intervals = (
        await session.execute(
            select(ActivityInterval).where(
                ActivityInterval.shift_id == shift_id, ActivityInterval.is_idle.is_(True)
            )
        )
    ).scalars().all()
    total = 0
    for iv in intervals:
        total += int((to_utc(iv.interval_end) - to_utc(iv.interval_start)).total_seconds())
    return total


def _compute_durations(shift: Shift, break_seconds: int, idle_seconds: int) -> DerivedDurations:
    policy = shift.policy_snapshot or {}
    late_grace = int(policy.get("late_threshold_min", 0)) * 60

    late = 0
    early = 0
    overtime = 0
    worked = 0

    start = to_utc(shift.actual_start) if shift.actual_start else None
    end = to_utc(shift.actual_end) if shift.actual_end else None
    sched_start = to_utc(shift.scheduled_start) if shift.scheduled_start else None
    sched_end = to_utc(shift.scheduled_end) if shift.scheduled_end else None

    if start and sched_start:
        delta = int((start - sched_start).total_seconds())
        # Late only counts beyond the grace threshold (docs/04 §5).
        late = max(0, delta - late_grace)

    # Idle counts against working time only when policy classifies it as non-working.
    idle_classification = (policy.get("monitoring", {}) or {}).get("idle_classification", "idle")
    idle_reduces_work = idle_classification != "working"

    if start and end:
        gross = int((end - start).total_seconds())
        worked = max(0, gross - break_seconds)
        if idle_reduces_work:
            worked = max(0, worked - idle_seconds)

    if end and sched_end:
        if end < sched_end:
            early = int((sched_end - end).total_seconds())
        elif end > sched_end and policy.get("allow_overtime", False):
            overtime = int((end - sched_end).total_seconds())

    return DerivedDurations(
        worked_seconds=worked,
        break_seconds=break_seconds,
        idle_seconds=idle_seconds,
        late_seconds=late,
        early_leave_seconds=early,
        overtime_seconds=overtime,
    )


def _derive_status(shift: Shift, d: DerivedDurations) -> str:
    if shift.state == MISSED:
        return MISSED_SHIFT
    if shift.state == CANCELLED:
        return REST_DAY
    if shift.state not in (COMPLETED, AUTO_COMPLETED, FORCE_STOPPED):
        # Not finished yet; treat as partial-in-progress snapshot.
        return PARTIAL
    if shift.actual_start is None:
        return ABSENT
    if d.overtime_seconds > 0:
        return OVERTIME
    if d.early_leave_seconds > 0:
        return EARLY_LEAVE
    if d.late_seconds > 0:
        return LATE
    return PRESENT


async def derive_for_shift(session: AsyncSession, shift: Shift) -> Attendance:
    """Recompute (or create) the attendance row for a shift's work date."""
    break_seconds = await _sum_breaks(session, shift.id)
    idle_seconds = await _sum_idle(session, shift.id)
    durations = _compute_durations(shift, break_seconds, idle_seconds)
    status = _derive_status(shift, durations)

    work_date = (
        to_utc(shift.scheduled_start).date()
        if shift.scheduled_start
        else (to_utc(shift.actual_start).date() if shift.actual_start else now().date())
    )

    existing = (
        await session.execute(
            select(Attendance).where(
                Attendance.organization_id == shift.organization_id,
                Attendance.employee_id == shift.employee_id,
                Attendance.work_date == work_date,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = Attendance(
            id=uuid.uuid4(),
            organization_id=shift.organization_id,
            employee_id=shift.employee_id,
            work_date=work_date,
        )
        session.add(existing)

    existing.shift_id = shift.id
    existing.status = status
    existing.scheduled_start = shift.scheduled_start
    existing.scheduled_end = shift.scheduled_end
    existing.actual_start = shift.actual_start
    existing.actual_end = shift.actual_end
    existing.worked_seconds = durations.worked_seconds
    existing.break_seconds = durations.break_seconds
    existing.idle_seconds = durations.idle_seconds
    existing.late_seconds = durations.late_seconds
    existing.early_leave_seconds = durations.early_leave_seconds
    existing.overtime_seconds = durations.overtime_seconds
    existing.computed_at = now()
    await session.flush()
    return existing
