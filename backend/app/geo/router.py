"""Geolocation / geofencing API (spec 75). Optional, opt-in, privacy-controlled.

All endpoints require geolocation to be enabled in org settings (settings.geo.enabled). Office
locations are managed by admins; the agent (device-auth) submits location pings that are
evaluated against the nearest office geofence. Location data is only ever stored when the
module is enabled.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.deps import DevicePrincipal, get_device_principal
from app.audit import service as audit
from app.auth.principal import Principal
from app.core.deps import get_tenant_session, require_permission
from app.core.tenant import open_tenant_session
from app.core.time_authority import now
from app.geo.distance import haversine_meters
from app.models.geo import GeofenceEvent, OfficeLocation
from app.models.organization import Organization

router = APIRouter(tags=["geo"])


async def _geo_enabled(session: AsyncSession, org_id: uuid.UUID) -> bool:
    org = (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    return bool(org and (org.settings or {}).get("geo", {}).get("enabled"))


class OfficeCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    radius_meters: int = 150


class OfficeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    latitude: float
    longitude: float
    radius_meters: int


class LocationPing(BaseModel):
    latitude: float
    longitude: float


class GeofenceResult(BaseModel):
    inside: bool
    nearest_location_id: uuid.UUID | None
    distance_meters: float | None


@router.post("/geo/offices", response_model=OfficeOut, status_code=201)
async def create_office(
    payload: OfficeCreate,
    principal: Principal = Depends(require_permission("settings.manage")),
    session: AsyncSession = Depends(get_tenant_session),
):
    if not await _geo_enabled(session, principal.organization_id):
        raise HTTPException(status_code=400, detail="geolocation module is not enabled")
    office = OfficeLocation(
        id=uuid.uuid4(), organization_id=principal.organization_id, **payload.model_dump()
    )
    session.add(office)
    await audit.record(
        session, action="geo.office.create", organization_id=principal.organization_id,
        actor_user_id=principal.user_id, target_type="office_location", target_id=office.id,
        new_value={"name": office.name},
    )
    await session.commit()
    return OfficeOut.model_validate(office)


@router.get("/geo/offices", response_model=list[OfficeOut])
async def list_offices(
    principal: Principal = Depends(require_permission("schedule.view")),
    session: AsyncSession = Depends(get_tenant_session),
):
    rows = (await session.execute(select(OfficeLocation))).scalars().all()
    return [OfficeOut.model_validate(o) for o in rows]


def evaluate_geofence(lat: float, lon: float, offices: list[OfficeLocation]):
    """Return (inside, nearest_office, distance) for the nearest office geofence."""
    nearest = None
    nearest_dist = None
    inside = False
    for o in offices:
        d = haversine_meters(lat, lon, o.latitude, o.longitude)
        if nearest_dist is None or d < nearest_dist:
            nearest_dist, nearest = d, o
        if d <= o.radius_meters:
            inside = True
    return inside, nearest, nearest_dist


@router.post("/agent/geo/ping", response_model=GeofenceResult)
async def location_ping(
    payload: LocationPing,
    dp: DevicePrincipal = Depends(get_device_principal),
):
    async with open_tenant_session(str(dp.organization_id)) as session:
        if not await _geo_enabled(session, dp.organization_id):
            raise HTTPException(status_code=400, detail="geolocation module is not enabled")
        offices = (await session.execute(select(OfficeLocation))).scalars().all()
        inside, nearest, dist = evaluate_geofence(payload.latitude, payload.longitude, offices)
        session.add(GeofenceEvent(
            id=uuid.uuid4(), organization_id=dp.organization_id, employee_id=dp.employee_id,
            device_id=dp.device_id, location_id=(nearest.id if nearest else None),
            latitude=payload.latitude, longitude=payload.longitude, inside=inside,
            distance_meters=dist, occurred_at=now(),
        ))
        await session.commit()
        return GeofenceResult(
            inside=inside,
            nearest_location_id=nearest.id if nearest else None,
            distance_meters=dist,
        )
