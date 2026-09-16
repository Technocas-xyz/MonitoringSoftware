"""Dashboard aggregation queries (spec 29/30/31/102).

Reads precomputed rollups + live shift state. Scope narrowing is applied by the caller's
principal so managers only see their teams.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directory import Employee
from app.models.productivity import DailyDepartmentRollup, DailyEmployeeRollup
from app.models.shifts import (
    ACTIVE_STATES,
    COMPLETED,
    ON_BREAK,
    WORKING,
    Attendance,
    Shift,
)


async def overview(
    session: AsyncSession, org_id: uuid.UUID, day: date, team_ids: set[uuid.UUID] | None = None
) -> dict:
    """Org/team live counts + averages for the admin dashboard (spec 102)."""
    emp_stmt = select(Employee).where(
        Employee.organization_id == org_id, Employee.status == "active"
    )
    if team_ids:
        emp_stmt = emp_stmt.where(Employee.team_id.in_(team_ids))
    employees = (await session.execute(emp_stmt)).scalars().all()
    emp_ids = [e.id for e in employees]
    total = len(employees)

    # Live shift states.
    working = on_break = not_started = 0
    if emp_ids:
        shifts = (
            await session.execute(
                select(Shift).where(
                    Shift.organization_id == org_id,
                    Shift.employee_id.in_(emp_ids),
                    Shift.state.in_(ACTIVE_STATES),
                )
            )
        ).scalars().all()
        active_by_emp = {s.employee_id: s.state for s in shifts}
        for e in employees:
            st = active_by_emp.get(e.id)
            if st == WORKING:
                working += 1
            elif st == ON_BREAK:
                on_break += 1
            else:
                not_started += 1

    # Average indicator from today's employee rollups.
    roll_stmt = select(DailyEmployeeRollup).where(
        DailyEmployeeRollup.organization_id == org_id,
        DailyEmployeeRollup.work_date == day,
    )
    if emp_ids:
        roll_stmt = roll_stmt.where(DailyEmployeeRollup.employee_id.in_(emp_ids))
    rollups = (await session.execute(roll_stmt)).scalars().all()
    avg_indicator = (
        round(sum(float(r.productivity_indicator) for r in rollups) / len(rollups), 2)
        if rollups else 0.0
    )
    avg_worked = (
        int(sum(r.worked_seconds for r in rollups) / len(rollups)) if rollups else 0
    )

    return {
        "employees": total,
        "working": working,
        "on_break": on_break,
        "not_started": not_started,
        "average_worked_seconds": avg_worked,
        "productivity_indicator": avg_indicator,
    }


async def employee_detail(
    session: AsyncSession, org_id: uuid.UUID, employee_id: uuid.UUID, day: date
) -> dict:
    """Employee detail dashboard (spec 30): today's attendance + productivity rollup."""
    att = (
        await session.execute(
            select(Attendance).where(
                Attendance.organization_id == org_id,
                Attendance.employee_id == employee_id,
                Attendance.work_date == day,
            )
        )
    ).scalar_one_or_none()
    roll = (
        await session.execute(
            select(DailyEmployeeRollup).where(
                DailyEmployeeRollup.organization_id == org_id,
                DailyEmployeeRollup.employee_id == employee_id,
                DailyEmployeeRollup.work_date == day,
            )
        )
    ).scalar_one_or_none()

    return {
        "employee_id": str(employee_id),
        "work_date": day.isoformat(),
        "attendance": {
            "status": att.status if att else None,
            "worked_seconds": att.worked_seconds if att else 0,
            "break_seconds": att.break_seconds if att else 0,
            "idle_seconds": att.idle_seconds if att else 0,
            "late_seconds": att.late_seconds if att else 0,
            "overtime_seconds": att.overtime_seconds if att else 0,
        },
        "productivity": {
            "tracked_seconds": roll.tracked_seconds if roll else 0,
            "productive_seconds": roll.productive_seconds if roll else 0,
            "neutral_seconds": roll.neutral_seconds if roll else 0,
            "unproductive_seconds": roll.unproductive_seconds if roll else 0,
            "indicator": float(roll.productivity_indicator) if roll else 0.0,
        },
    }


async def department_analytics(
    session: AsyncSession, org_id: uuid.UUID, department_id: uuid.UUID, day: date
) -> dict:
    """Department analytics (spec 31) from the department rollup."""
    roll = (
        await session.execute(
            select(DailyDepartmentRollup).where(
                DailyDepartmentRollup.organization_id == org_id,
                DailyDepartmentRollup.department_id == department_id,
                DailyDepartmentRollup.work_date == day,
            )
        )
    ).scalar_one_or_none()
    if roll is None:
        return {"department_id": str(department_id), "work_date": day.isoformat(), "employees": 0}
    tracked = roll.tracked_seconds or 0
    def pct(x):
        return round(100.0 * x / tracked, 1) if tracked else 0.0
    return {
        "department_id": str(department_id),
        "work_date": day.isoformat(),
        "employees": roll.employees,
        "tracked_seconds": tracked,
        "productive_pct": pct(roll.productive_seconds),
        "neutral_pct": pct(roll.neutral_seconds),
        "unproductive_pct": pct(roll.unproductive_seconds),
        "idle_seconds": roll.idle_seconds,
        "productivity_indicator": float(roll.productivity_indicator),
    }
