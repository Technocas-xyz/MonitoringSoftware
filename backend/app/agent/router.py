"""Agent-facing endpoints (device-authenticated): shift sync, schedule, heartbeat.

All routes require a valid device token + request signature (get_device_principal). The
device may only act for its own employee. Responses give the agent exactly what its tray UI
and collectors need, with the server as the authority for state and time.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.deps import DevicePrincipal, get_device_principal
from app.core.tenant import open_tenant_session
from app.core.time_authority import now
from app.models.directory import Employee
from app.models.shifts import ACTIVE_STATES, Shift
from app.scheduling.resolver import occurrences_for

router = APIRouter(prefix="/agent", tags=["agent"])


class CurrentShiftOut(BaseModel):
    shift_id: uuid.UUID | None
    state: str | None
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    actual_start: datetime | None
    timezone: str | None
    monitoring: dict | None
    server_time: datetime


class ScheduleWindowOut(BaseModel):
    scheduled_start: datetime
    scheduled_end: datetime


class TodayScheduleOut(BaseModel):
    day: date
    timezone: str | None
    windows: list[ScheduleWindowOut]
    server_time: datetime


class HeartbeatIn(BaseModel):
    shift_id: uuid.UUID | None = None
    agent_version: str | None = None
    os: str | None = None
    online: bool = True
    tracking_state: str | None = None
    timestamp: datetime | None = None
    net: dict | None = None


@router.get("/shift/current", response_model=CurrentShiftOut)
async def current_shift(dp: DevicePrincipal = Depends(get_device_principal)):
    async with open_tenant_session(str(dp.organization_id)) as session:
        shift = (
            await session.execute(
                select(Shift).where(
                    Shift.employee_id == dp.employee_id,
                    Shift.state.in_(ACTIVE_STATES),
                )
            )
        ).scalars().first()
        if shift is None:
            return CurrentShiftOut(
                shift_id=None, state=None, scheduled_start=None, scheduled_end=None,
                actual_start=None, timezone=None, monitoring=None, server_time=now(),
            )
        monitoring = (shift.policy_snapshot or {}).get("monitoring")
        return CurrentShiftOut(
            shift_id=shift.id,
            state=shift.state,
            scheduled_start=shift.scheduled_start,
            scheduled_end=shift.scheduled_end,
            actual_start=shift.actual_start,
            timezone=shift.timezone,
            monitoring=monitoring,
            server_time=now(),
        )


@router.get("/schedule/today", response_model=TodayScheduleOut)
async def today_schedule(dp: DevicePrincipal = Depends(get_device_principal)):
    async with open_tenant_session(str(dp.organization_id)) as session:
        emp = (
            await session.execute(select(Employee).where(Employee.id == dp.employee_id))
        ).scalar_one_or_none()
        server_now = now()
        if emp is None:
            return TodayScheduleOut(
                day=server_now.date(), timezone=None, windows=[], server_time=server_now
            )
        _schedule, occs, tz = await occurrences_for(session, emp, server_now.date())
        return TodayScheduleOut(
            day=server_now.date(),
            timezone=tz,
            windows=[
                ScheduleWindowOut(scheduled_start=o.scheduled_start, scheduled_end=o.scheduled_end)
                for o in occs
            ],
            server_time=server_now,
        )


@router.post("/heartbeat")
async def heartbeat(payload: HeartbeatIn, dp: DevicePrincipal = Depends(get_device_principal)):
    async with open_tenant_session(str(dp.organization_id)) as session:
        from app.models.devices import Device

        device = (
            await session.execute(select(Device).where(Device.id == dp.device_id))
        ).scalar_one()
        device.last_seen_at = now()
        if payload.agent_version:
            device.agent_version = payload.agent_version
        if payload.tracking_state:
            device.tracking_state = payload.tracking_state
        await session.commit()
    # Presence fan-out to Redis/WS gateway is wired in Phase 5.
    return {"ok": True, "server_time": now().isoformat()}
