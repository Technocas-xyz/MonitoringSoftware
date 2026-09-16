"""Report builders (spec 37). Each returns (columns, rows) from authoritative data.

Report types: attendance, productivity, application, website, shift. Filters narrow by date
range and (optionally) employee. Builders read derived attendance/rollups + event tables.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import ApplicationEvent, WebsiteEvent
from app.models.productivity import DailyEmployeeRollup
from app.models.shifts import Attendance, Shift


@dataclass
class ReportData:
    title: str
    columns: list[str]
    rows: list[list]


def _fmt_secs(s: int | None) -> str:
    s = int(s or 0)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


async def attendance_report(session, org_id, from_date, to_date, employee_id=None) -> ReportData:
    stmt = select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.work_date >= from_date,
        Attendance.work_date <= to_date,
    )
    if employee_id:
        stmt = stmt.where(Attendance.employee_id == employee_id)
    rows = (await session.execute(stmt.order_by(Attendance.work_date))).scalars().all()
    return ReportData(
        title="Attendance Report",
        columns=["Employee", "Date", "Status", "Worked", "Break", "Late", "Early Leave", "Overtime"],
        rows=[
            [str(a.employee_id), a.work_date.isoformat(), a.status,
             _fmt_secs(a.worked_seconds), _fmt_secs(a.break_seconds),
             _fmt_secs(a.late_seconds), _fmt_secs(a.early_leave_seconds), _fmt_secs(a.overtime_seconds)]
            for a in rows
        ],
    )


async def productivity_report(session, org_id, from_date, to_date, employee_id=None) -> ReportData:
    stmt = select(DailyEmployeeRollup).where(
        DailyEmployeeRollup.organization_id == org_id,
        DailyEmployeeRollup.work_date >= from_date,
        DailyEmployeeRollup.work_date <= to_date,
    )
    if employee_id:
        stmt = stmt.where(DailyEmployeeRollup.employee_id == employee_id)
    rows = (await session.execute(stmt.order_by(DailyEmployeeRollup.work_date))).scalars().all()
    return ReportData(
        title="Productivity Report",
        columns=["Employee", "Date", "Tracked", "Productive", "Neutral", "Unproductive", "Idle", "Indicator"],
        rows=[
            [str(r.employee_id), r.work_date.isoformat(), _fmt_secs(r.tracked_seconds),
             _fmt_secs(r.productive_seconds), _fmt_secs(r.neutral_seconds),
             _fmt_secs(r.unproductive_seconds), _fmt_secs(r.idle_seconds),
             f"{float(r.productivity_indicator)}%"]
            for r in rows
        ],
    )


def _bounds(from_date: date, to_date: date):
    return (
        datetime.combine(from_date, time.min, tzinfo=timezone.utc),
        datetime.combine(to_date, time.max, tzinfo=timezone.utc),
    )


async def application_report(session, org_id, from_date, to_date, employee_id=None) -> ReportData:
    start, end = _bounds(from_date, to_date)
    stmt = (
        select(
            ApplicationEvent.employee_id,
            ApplicationEvent.application,
            func.sum(ApplicationEvent.duration_seconds),
        )
        .where(
            ApplicationEvent.organization_id == org_id,
            ApplicationEvent.occurred_at >= start,
            ApplicationEvent.occurred_at <= end,
        )
        .group_by(ApplicationEvent.employee_id, ApplicationEvent.application)
    )
    if employee_id:
        stmt = stmt.where(ApplicationEvent.employee_id == employee_id)
    rows = (await session.execute(stmt)).all()
    return ReportData(
        title="Application Report",
        columns=["Employee", "Application", "Duration"],
        rows=[[str(emp), app, _fmt_secs(dur)] for emp, app, dur in rows],
    )


async def website_report(session, org_id, from_date, to_date, employee_id=None) -> ReportData:
    start, end = _bounds(from_date, to_date)
    stmt = (
        select(
            WebsiteEvent.employee_id, WebsiteEvent.domain, func.sum(WebsiteEvent.duration_seconds)
        )
        .where(
            WebsiteEvent.organization_id == org_id,
            WebsiteEvent.occurred_at >= start,
            WebsiteEvent.occurred_at <= end,
        )
        .group_by(WebsiteEvent.employee_id, WebsiteEvent.domain)
    )
    if employee_id:
        stmt = stmt.where(WebsiteEvent.employee_id == employee_id)
    rows = (await session.execute(stmt)).all()
    return ReportData(
        title="Website Report",
        columns=["Employee", "Domain", "Duration"],
        rows=[[str(emp), dom, _fmt_secs(dur)] for emp, dom, dur in rows],
    )


async def shift_report(session, org_id, from_date, to_date, employee_id=None) -> ReportData:
    start, end = _bounds(from_date, to_date)
    stmt = select(Shift).where(
        Shift.organization_id == org_id,
        Shift.scheduled_start >= start,
        Shift.scheduled_start <= end,
    )
    if employee_id:
        stmt = stmt.where(Shift.employee_id == employee_id)
    rows = (await session.execute(stmt.order_by(Shift.scheduled_start))).scalars().all()
    return ReportData(
        title="Shift Report",
        columns=["Employee", "State", "Scheduled Start", "Scheduled End", "Actual Start", "Actual End"],
        rows=[
            [str(s.employee_id), s.state,
             s.scheduled_start.isoformat() if s.scheduled_start else "",
             s.scheduled_end.isoformat() if s.scheduled_end else "",
             s.actual_start.isoformat() if s.actual_start else "",
             s.actual_end.isoformat() if s.actual_end else ""]
            for s in rows
        ],
    )


BUILDERS = {
    "attendance": attendance_report,
    "productivity": productivity_report,
    "application": application_report,
    "website": website_report,
    "shift": shift_report,
}


async def build(session: AsyncSession, report_type: str, org_id: uuid.UUID,
                from_date: date, to_date: date, employee_id: uuid.UUID | None = None) -> ReportData:
    builder = BUILDERS.get(report_type)
    if builder is None:
        raise ValueError(f"unknown report type: {report_type}")
    return await builder(session, org_id, from_date, to_date, employee_id)
