"""Alert rule engine (spec 35/36).

Evaluates enabled alert rules for an organization against authoritative attendance + rollup
state for a day and creates deduplicated alerts. Each rule kind has a threshold in
rule.params. Alerts are idempotent via a dedup_key = f"{rule_key}:{employee_id}:{day}" so
repeated evaluation does not spam duplicates.

Rule kinds (spec 35):
  late_arrival          params.threshold_seconds  (attendance.late_seconds >)
  excessive_idle        params.threshold_seconds  (attendance.idle_seconds >)
  excessive_unproductive params.threshold_seconds (rollup.unproductive_seconds >)
  missed_shift          attendance.status == MISSED_SHIFT
  early_departure       attendance.early_leave_seconds > 0
  monitoring_lost       consumed from audit (raised by scheduler.detect_monitoring_lost)
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.alerts import Alert, AlertRule
from app.models.directory import Employee
from app.models.productivity import DailyEmployeeRollup
from app.models.shifts import Attendance
from app.notifications import service as notifications

log = get_logger("alerts")

LATE_ARRIVAL = "late_arrival"
EXCESSIVE_IDLE = "excessive_idle"
EXCESSIVE_UNPRODUCTIVE = "excessive_unproductive"
MISSED_SHIFT = "missed_shift"
EARLY_DEPARTURE = "early_departure"


async def _create_alert(
    session: AsyncSession, org_id: uuid.UUID, rule: AlertRule, employee_id: uuid.UUID,
    message: str, context: dict, dedup_key: str,
) -> Alert | None:
    existing = (
        await session.execute(
            select(Alert).where(Alert.organization_id == org_id, Alert.dedup_key == dedup_key)
        )
    ).scalar_one_or_none()
    if existing:
        return None  # idempotent: already alerted for this occurrence
    alert = Alert(
        id=uuid.uuid4(), organization_id=org_id, rule_id=rule.id, employee_id=employee_id,
        severity=rule.severity, message=message, context=context, status="open",
        dedup_key=dedup_key,
    )
    session.add(alert)
    await session.flush()

    # Dispatch to the rule's channels (manager notifications handled by recipient resolution
    # elsewhere; here we surface an in-app/dashboard notification with the alert body).
    await notifications.dispatch(
        session, org_id,
        template_key=rule.key, channels=rule.channels or ["in_app"],
        recipient_user_id=None, context=context, fallback_body=message,
    )
    return alert


async def evaluate_org(session: AsyncSession, org_id: uuid.UUID, day: date) -> int:
    rules = (
        await session.execute(
            select(AlertRule).where(
                AlertRule.organization_id == org_id, AlertRule.enabled.is_(True)
            )
        )
    ).scalars().all()
    if not rules:
        return 0

    attendance = {
        (a.employee_id): a
        for a in (
            await session.execute(
                select(Attendance).where(
                    Attendance.organization_id == org_id, Attendance.work_date == day
                )
            )
        ).scalars().all()
    }
    rollups = {
        r.employee_id: r
        for r in (
            await session.execute(
                select(DailyEmployeeRollup).where(
                    DailyEmployeeRollup.organization_id == org_id,
                    DailyEmployeeRollup.work_date == day,
                )
            )
        ).scalars().all()
    }

    created = 0
    for rule in rules:
        threshold = int(rule.params.get("threshold_seconds", 0)) if rule.params else 0
        for emp_id, att in attendance.items():
            dedup = f"{rule.key}:{emp_id}:{day.isoformat()}"
            fire = False
            message = ""
            ctx = {"employee_id": str(emp_id), "work_date": day.isoformat()}

            if rule.key == LATE_ARRIVAL and att.late_seconds > threshold:
                fire, message = True, f"Late arrival: {att.late_seconds // 60} min"
                ctx["late_minutes"] = att.late_seconds // 60
            elif rule.key == EXCESSIVE_IDLE and att.idle_seconds > threshold:
                fire, message = True, f"Excessive idle: {att.idle_seconds // 60} min"
                ctx["idle_minutes"] = att.idle_seconds // 60
            elif rule.key == EARLY_DEPARTURE and att.early_leave_seconds > 0:
                fire, message = True, f"Early departure: {att.early_leave_seconds // 60} min"
                ctx["early_minutes"] = att.early_leave_seconds // 60
            elif rule.key == MISSED_SHIFT and att.status == "MISSED_SHIFT":
                fire, message = True, "Missed shift"
            elif rule.key == EXCESSIVE_UNPRODUCTIVE:
                roll = rollups.get(emp_id)
                if roll and roll.unproductive_seconds > threshold:
                    fire = True
                    message = f"Excessive unproductive activity: {roll.unproductive_seconds // 60} min"
                    ctx["unproductive_minutes"] = roll.unproductive_seconds // 60

            if fire:
                a = await _create_alert(session, org_id, rule, emp_id, message, ctx, dedup)
                if a:
                    created += 1

    await session.flush()
    return created
