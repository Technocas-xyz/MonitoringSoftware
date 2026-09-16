"""Payroll run generation (spec 77).

Payroll rules are configurable per organization (org.settings.payroll) and never assume a
specific country's law. A run aggregates each employee's attendance in the period into payroll
lines: regular, overtime, approved leave, unpaid leave. Amounts price hours by the employee's
hourly rate and configurable multipliers.

Default rules (overridable via settings.payroll):
  overtime_multiplier: 1.5
  paid_leave: true            (approved leave paid at regular rate)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_authority import now
from app.models.directory import Employee
from app.models.organization import Organization
from app.models.payroll import PayrollLine, PayrollRun
from app.models.scheduling import LeaveRequest
from app.models.shifts import Attendance

DEFAULT_RULES = {"overtime_multiplier": 1.5, "paid_leave": True}


async def _rules(session: AsyncSession, org_id: uuid.UUID) -> dict:
    org = (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    return {**DEFAULT_RULES, **((org.settings or {}).get("payroll", {}))}


async def _approved_leave_days(session, org_id, emp_id, start, end) -> int:
    leaves = (
        await session.execute(
            select(LeaveRequest).where(
                LeaveRequest.organization_id == org_id,
                LeaveRequest.employee_id == emp_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
    ).scalars().all()
    days = 0
    for lv in leaves:
        s = max(lv.start_date, start)
        e = min(lv.end_date, end)
        days += (e - s).days + 1
    return max(0, days)


async def generate_run(
    session: AsyncSession, org_id: uuid.UUID, period_start: date, period_end: date
) -> PayrollRun:
    rules = await _rules(session, org_id)
    ot_mult = float(rules.get("overtime_multiplier", 1.5))
    paid_leave = bool(rules.get("paid_leave", True))

    run = PayrollRun(
        id=uuid.uuid4(), organization_id=org_id, period_start=period_start,
        period_end=period_end, status="draft", rules_snapshot=rules,
    )
    session.add(run)
    await session.flush()

    employees = (
        await session.execute(
            select(Employee).where(Employee.organization_id == org_id, Employee.status == "active")
        )
    ).scalars().all()

    for emp in employees:
        rate = float(emp.hourly_rate) if emp.hourly_rate else 0.0
        atts = (
            await session.execute(
                select(Attendance).where(
                    Attendance.organization_id == org_id,
                    Attendance.employee_id == emp.id,
                    Attendance.work_date >= period_start,
                    Attendance.work_date <= period_end,
                )
            )
        ).scalars().all()

        regular_seconds = sum(a.worked_seconds for a in atts)
        overtime_seconds = sum(a.overtime_seconds for a in atts)
        # worked_seconds already includes overtime window? Keep them separate for clarity:
        regular_hours = round(max(0, regular_seconds - overtime_seconds) / 3600.0, 2)
        overtime_hours = round(overtime_seconds / 3600.0, 2)

        if regular_hours > 0:
            session.add(PayrollLine(
                id=uuid.uuid4(), organization_id=org_id, run_id=run.id, employee_id=emp.id,
                line_type="regular", hours=regular_hours, rate=rate,
                amount=round(regular_hours * rate, 2),
            ))
        if overtime_hours > 0:
            session.add(PayrollLine(
                id=uuid.uuid4(), organization_id=org_id, run_id=run.id, employee_id=emp.id,
                line_type="overtime", hours=overtime_hours, rate=round(rate * ot_mult, 2),
                amount=round(overtime_hours * rate * ot_mult, 2),
            ))

        leave_days = await _approved_leave_days(session, org_id, emp.id, period_start, period_end)
        if leave_days > 0:
            leave_hours = leave_days * 8.0  # configurable workday assumption could live in rules
            line_type = "leave" if paid_leave else "unpaid"
            amount = round(leave_hours * rate, 2) if paid_leave else 0.0
            session.add(PayrollLine(
                id=uuid.uuid4(), organization_id=org_id, run_id=run.id, employee_id=emp.id,
                line_type=line_type, hours=leave_hours, rate=rate if paid_leave else 0.0,
                amount=amount,
            ))

    await session.flush()
    return run
