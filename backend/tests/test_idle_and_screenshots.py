"""Idle fold into attendance + screenshot access logging / RBAC."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.monitoring import ActivityInterval, ScreenshotAccessLog
from app.models.shifts import COMPLETED, Shift
from app.shifts.attendance import derive_for_shift
from tests.conftest import auth_header, login
from tests.factories import make_org_and_employee


@pytest.mark.asyncio
async def test_idle_reduces_worked_time(session_factory):
    org_id, emp_id = await make_org_and_employee()
    start = now() - timedelta(hours=2)
    end = now()
    async with get_sessionmaker()() as s:
        shift = Shift(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, state=COMPLETED,
            scheduled_start=start, scheduled_end=end, actual_start=start, actual_end=end,
            timezone="UTC",
            policy_snapshot={"late_threshold_min": 15, "allow_overtime": True,
                             "monitoring": {"idle_classification": "idle"}},
            version=1,
        )
        s.add(shift)
        await s.flush()
        # 20 minutes idle
        s.add(ActivityInterval(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            shift_id=shift.id, interval_start=start, interval_end=start + timedelta(minutes=20),
            is_idle=True, occurred_at=start, event_key="idle-1",
        ))
        await s.flush()
        att = await derive_for_shift(s, shift)
        await s.commit()
        assert att.idle_seconds == 20 * 60
        # gross ~2h, worked reduced by idle
        assert att.worked_seconds <= (2 * 3600) - (20 * 60) + 1


@pytest.mark.asyncio
async def test_idle_not_subtracted_when_classified_working(session_factory):
    org_id, emp_id = await make_org_and_employee()
    start = now() - timedelta(hours=1)
    end = now()
    async with get_sessionmaker()() as s:
        shift = Shift(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, state=COMPLETED,
            scheduled_start=start, scheduled_end=end, actual_start=start, actual_end=end,
            timezone="UTC",
            policy_snapshot={"monitoring": {"idle_classification": "working"}}, version=1,
        )
        s.add(shift)
        await s.flush()
        s.add(ActivityInterval(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            shift_id=shift.id, interval_start=start, interval_end=start + timedelta(minutes=10),
            is_idle=True, occurred_at=start, event_key="idle-2",
        ))
        await s.flush()
        att = await derive_for_shift(s, shift)
        await s.commit()
        assert att.idle_seconds == 10 * 60
        assert att.worked_seconds >= 3600 - 5  # idle not subtracted


# --- screenshot access logging via HTTP ---
async def _admin_and_screenshot(client, super_admin):
    root = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    await client.post(
        "/api/v1/organizations", headers=auth_header(root),
        json={"name": "Acme", "slug": "acme", "timezone": "UTC",
              "admin_email": "admin@acme.test", "admin_password": "acmepass123", "admin_full_name": "A"},
    )
    admin = await login(client, "acme", "admin@acme.test", "acmepass123")
    h = auth_header(admin)
    emp = await client.post("/api/v1/employees", headers=h, json={"full_name": "S"})
    emp_id = emp.json()["id"]
    # Insert a stored screenshot directly (device upload path is exercised in agent tests).
    async with get_sessionmaker()() as s:
        from app.models.monitoring import Screenshot
        me = (await client.get("/api/v1/auth/me", headers=h)).json()
        shot = Screenshot(
            id=uuid.uuid4(), organization_id=uuid.UUID(me["organization_id"]),
            employee_id=uuid.UUID(emp_id), device_id=uuid.uuid4(),
            storage_key="k/x.webp", captured_at=now(), status="stored",
            occurred_at=now(), event_key="shot-1",
        )
        s.add(shot)
        await s.commit()
        return h, shot.id


@pytest.mark.asyncio
async def test_screenshot_view_is_logged(client, super_admin):
    h, shot_id = await _admin_and_screenshot(client, super_admin)
    resp = await client.get(f"/api/v1/screenshots/{shot_id}/url", headers=h)
    assert resp.status_code == 200, resp.text
    assert "url" in resp.json()
    async with get_sessionmaker()() as s:
        logs = (await s.execute(select(ScreenshotAccessLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "view"


@pytest.mark.asyncio
async def test_screenshot_download_requires_permission(client, super_admin):
    # HR has screenshot.view but NOT screenshot.download in the seed matrix (doc 07).
    h, shot_id = await _admin_and_screenshot(client, super_admin)
    # create an HR user
    hr = await client.post(
        "/api/v1/users", headers=h,
        json={"email": "hr@acme.test", "full_name": "HR", "password": "hrpass1234", "role_keys": ["hr"]},
    )
    assert hr.status_code == 201, hr.text
    hr_token = await login(client, "acme", "hr@acme.test", "hrpass1234")
    hr_h = auth_header(hr_token)

    # HR can view
    view = await client.get(f"/api/v1/screenshots/{shot_id}/url", headers=hr_h)
    assert view.status_code == 200, view.text
    # HR cannot download
    dl = await client.get(f"/api/v1/screenshots/{shot_id}/url?download=true", headers=hr_h)
    assert dl.status_code == 403
