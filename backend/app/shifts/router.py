"""Shifts API (spec 51). Server-authoritative; client requests, server validates + records.

Employees control their own shift (shift.start_own / shift.control_own). Managers/HR can
force-stop (shift.force_stop). All reads require shift.view.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.core.deps import get_principal, get_tenant_session, require_permission
from app.models.directory import Employee
from app.models.shifts import Shift, ShiftEvent
from app.shifts import errors, service
from app.shifts.schemas import (
    ForceStopRequest,
    ShiftActionRequest,
    ShiftCreateRequest,
    ShiftEventOut,
    ShiftOut,
)

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _raise(err: errors.ShiftError):
    raise HTTPException(status_code=err.status_code, detail={"code": err.code, "detail": err.detail})


async def _load_employee(session: AsyncSession, employee_id: uuid.UUID) -> Employee:
    emp = (
        await session.execute(select(Employee).where(Employee.id == employee_id))
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="employee not found")
    return emp


async def _own_employee(session: AsyncSession, principal: Principal) -> Employee:
    emp = (
        await session.execute(
            select(Employee).where(Employee.user_id == principal.user_id)
        )
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(status_code=404, detail="no employee linked to this user")
    return emp


def _ensure_owns(shift: Shift, employee: Employee):
    if shift.employee_id != employee.id:
        raise HTTPException(status_code=403, detail="not your shift")


@router.post("", response_model=ShiftOut, status_code=201)
async def create_shift(
    payload: ShiftCreateRequest,
    principal: Principal = Depends(require_permission("schedule.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    emp = await _load_employee(session, payload.employee_id)
    try:
        shift = await service.create_shift_for_day(session, emp, payload.day)
    except errors.ShiftError as e:
        _raise(e)
    await session.commit()
    return ShiftOut.model_validate(shift)


@router.get("/{shift_id}", response_model=ShiftOut)
async def get_shift(
    shift_id: uuid.UUID,
    principal: Principal = Depends(require_permission("shift.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        shift = await service.get_shift(session, shift_id)
    except errors.ShiftError as e:
        _raise(e)
    return ShiftOut.model_validate(shift)


@router.get("/{shift_id}/events", response_model=list[ShiftEventOut])
async def list_events(
    shift_id: uuid.UUID,
    principal: Principal = Depends(require_permission("shift.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (
        await session.execute(
            select(ShiftEvent).where(ShiftEvent.shift_id == shift_id).order_by(ShiftEvent.occurred_at)
        )
    ).scalars().all()
    return [ShiftEventOut.model_validate(e) for e in rows]


async def _action(session, principal, shift_id, fn, **kw):
    shift = await service.get_shift(session, shift_id)
    emp = await _own_employee(session, principal)
    _ensure_owns(shift, emp)
    result = await fn(session, shift, actor_user_id=principal.user_id, **kw)
    await session.commit()
    return ShiftOut.model_validate(result)


@router.post("/{shift_id}/start", response_model=ShiftOut)
async def start_shift(
    shift_id: uuid.UUID,
    payload: ShiftActionRequest,
    principal: Principal = Depends(require_permission("shift.start_own")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        return await _action(
            session, principal, shift_id, service.start,
            device_id=payload.device_id, client_time=payload.client_time, event_id=payload.event_id,
        )
    except errors.ShiftError as e:
        _raise(e)


@router.post("/{shift_id}/pause", response_model=ShiftOut)
async def pause_shift(
    shift_id: uuid.UUID,
    payload: ShiftActionRequest,
    principal: Principal = Depends(require_permission("shift.control_own")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        return await _action(
            session, principal, shift_id, service.pause,
            is_break=payload.is_break, device_id=payload.device_id,
            client_time=payload.client_time, event_id=payload.event_id,
        )
    except errors.ShiftError as e:
        _raise(e)


@router.post("/{shift_id}/resume", response_model=ShiftOut)
async def resume_shift(
    shift_id: uuid.UUID,
    payload: ShiftActionRequest,
    principal: Principal = Depends(require_permission("shift.control_own")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        return await _action(
            session, principal, shift_id, service.resume,
            device_id=payload.device_id, client_time=payload.client_time, event_id=payload.event_id,
        )
    except errors.ShiftError as e:
        _raise(e)


@router.post("/{shift_id}/end", response_model=ShiftOut)
async def end_shift(
    shift_id: uuid.UUID,
    payload: ShiftActionRequest,
    principal: Principal = Depends(require_permission("shift.control_own")),
    session: AsyncSession = Depends(get_tenant_session),
):
    try:
        return await _action(
            session, principal, shift_id, service.end,
            device_id=payload.device_id, client_time=payload.client_time, event_id=payload.event_id,
        )
    except errors.ShiftError as e:
        _raise(e)


@router.post("/{shift_id}/force-stop", response_model=ShiftOut)
async def force_stop_shift(
    shift_id: uuid.UUID,
    payload: ForceStopRequest,
    principal: Principal = Depends(require_permission("shift.force_stop")),
    session: AsyncSession = Depends(get_tenant_session),
):
    # Manager action: no ownership check; permission-gated only.
    try:
        shift = await service.get_shift(session, shift_id)
        result = await service.end(
            session, shift, actor_user_id=principal.user_id, forced=True,
            reason=payload.reason, event_id=payload.event_id,
        )
        await session.commit()
        return ShiftOut.model_validate(result)
    except errors.ShiftError as e:
        _raise(e)
