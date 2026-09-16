"""Phase 9: SSO callback, geofence haversine, payroll line math, settings + RBAC gates."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.geo.distance import haversine_meters
from app.geo.router import evaluate_geofence
from app.models.geo import OfficeLocation
from app.models.payroll import PayrollLine
from app.models.shifts import Attendance
from app.payroll.service import generate_run
from tests.conftest import auth_header, login
from tests.factories import make_org_and_employee


# ---- geofence math (pure) ----
def test_haversine_known_distance():
    # ~111 km per degree of latitude near the equator
    d = haversine_meters(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_evaluate_geofence_inside_and_outside():
    office = OfficeLocation(
        id=uuid.uuid4(), organization_id=uuid.uuid4(), name="HQ",
        latitude=24.8607, longitude=67.0011, radius_meters=200,
    )
    # ~same point -> inside
    inside, nearest, dist = evaluate_geofence(24.8607, 67.0011, [office])
    assert inside is True
    assert nearest.id == office.id
    assert dist < 1
    # far away -> outside
    inside2, _, dist2 = evaluate_geofence(25.0, 67.5, [office])
    assert inside2 is False
    assert dist2 > 200


# ---- payroll math ----
@pytest.mark.asyncio
async def test_payroll_generates_regular_and_overtime_lines(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        # set an hourly rate
        from app.models.directory import Employee
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        emp.hourly_rate = 20.0
        # attendance: 10h worked incl 2h overtime -> 8h regular @20, 2h OT @30 (1.5x)
        s.add(Attendance(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id,
            work_date=now().date(), status="OVERTIME",
            worked_seconds=10 * 3600, break_seconds=0, idle_seconds=0,
            late_seconds=0, early_leave_seconds=0, overtime_seconds=2 * 3600, computed_at=now(),
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        d = now().date()
        run = await generate_run(s, org_id, d, d)
        await s.commit()
        lines = (await s.execute(select(PayrollLine).where(PayrollLine.run_id == run.id))).scalars().all()
        by_type = {line.line_type: line for line in lines}
        assert "regular" in by_type and "overtime" in by_type
        assert float(by_type["regular"].hours) == 8.0
        assert float(by_type["regular"].amount) == 160.0        # 8 * 20
        assert float(by_type["overtime"].hours) == 2.0
        assert float(by_type["overtime"].amount) == 60.0        # 2 * 20 * 1.5


# ---- HTTP: settings + SSO + RBAC ----
async def _admin(client, super_admin):
    root = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    await client.post(
        "/api/v1/organizations", headers=auth_header(root),
        json={"name": "Acme", "slug": "acme", "timezone": "UTC",
              "admin_email": "admin@acme.test", "admin_password": "acmepass123", "admin_full_name": "A"},
    )
    admin = await login(client, "acme", "admin@acme.test", "acmepass123")
    return auth_header(admin)


@pytest.mark.asyncio
async def test_sso_disabled_by_default_then_enabled(client, super_admin):
    h = await _admin(client, super_admin)
    # callback fails when SSO not enabled
    body = {"organization_slug": "acme", "provider": "stub", "code": "subj-1|new@acme.test|New User",
            "redirect_uri": "https://app.local/cb"}
    denied = await client.post("/api/v1/auth/sso/stub/callback", json=body)
    assert denied.status_code == 400

    # enable SSO via settings
    en = await client.patch("/api/v1/settings", headers=h,
                            json={"settings": {"sso": {"enabled": True, "providers": ["stub"]}}})
    assert en.status_code == 200

    ok = await client.post("/api/v1/auth/sso/stub/callback", json=body)
    assert ok.status_code == 200, ok.text
    assert "access_token" in ok.json()


@pytest.mark.asyncio
async def test_geo_ping_requires_module_enabled(client, super_admin):
    h = await _admin(client, super_admin)
    # creating an office is blocked until geo enabled
    blocked = await client.post("/api/v1/geo/offices", headers=h,
                                json={"name": "HQ", "latitude": 1.0, "longitude": 1.0})
    assert blocked.status_code == 400
    await client.patch("/api/v1/settings", headers=h, json={"settings": {"geo": {"enabled": True}}})
    ok = await client.post("/api/v1/geo/offices", headers=h,
                           json={"name": "HQ", "latitude": 1.0, "longitude": 1.0, "radius_meters": 100})
    assert ok.status_code == 201, ok.text


@pytest.mark.asyncio
async def test_payroll_requires_permission(client, super_admin):
    h = await _admin(client, super_admin)
    # employee has no payroll.run
    await client.post(
        "/api/v1/users", headers=h,
        json={"email": "e@acme.test", "full_name": "E", "password": "emppass123", "role_keys": ["employee"]},
    )
    emp_token = await login(client, "acme", "e@acme.test", "emppass123")
    denied = await client.post(
        "/api/v1/payroll/runs", headers=auth_header(emp_token),
        json={"period_start": "2026-09-01", "period_end": "2026-09-07"},
    )
    assert denied.status_code == 403
    # org_admin can run
    ok = await client.post(
        "/api/v1/payroll/runs", headers=h,
        json={"period_start": "2026-09-01", "period_end": "2026-09-07"},
    )
    assert ok.status_code == 201, ok.text
