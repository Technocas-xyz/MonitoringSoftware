"""Projects, task timers, timesheet lifecycle, corrections, costing RBAC."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from tests.conftest import auth_header, login


async def _admin_and_employee_user(client, super_admin):
    root = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    await client.post(
        "/api/v1/organizations", headers=auth_header(root),
        json={"name": "Acme", "slug": "acme", "timezone": "UTC",
              "admin_email": "admin@acme.test", "admin_password": "acmepass123", "admin_full_name": "A"},
    )
    admin = await login(client, "acme", "admin@acme.test", "acmepass123")
    h = auth_header(admin)
    u = await client.post(
        "/api/v1/users", headers=h,
        json={"email": "emp@acme.test", "full_name": "Emp", "password": "emppass123", "role_keys": ["employee"]},
    )
    user_id = u.json()["id"]
    await client.post("/api/v1/employees", headers=h, json={"full_name": "Emp", "user_id": user_id})
    emp_token = await login(client, "acme", "emp@acme.test", "emppass123")
    return h, auth_header(emp_token)


@pytest.mark.asyncio
async def test_task_timer_switch_closes_prior_entry(client, super_admin):
    admin_h, emp_h = await _admin_and_employee_user(client, super_admin)
    proj = await client.post("/api/v1/projects", headers=admin_h, json={"name": "Campus Connect"})
    pid = proj.json()["id"]
    t1 = await client.post("/api/v1/tasks", headers=admin_h, json={"project_id": pid, "name": "Attendance"})
    t2 = await client.post("/api/v1/tasks", headers=admin_h, json={"project_id": pid, "name": "Mobile"})
    t1_id, t2_id = t1.json()["id"], t2.json()["id"]

    s1 = await client.post(f"/api/v1/tasks/{t1_id}/start", headers=emp_h)
    assert s1.status_code == 200, s1.text
    assert s1.json()["ended_at"] is None

    # starting a second task closes the first open entry
    s2 = await client.post(f"/api/v1/tasks/{t2_id}/start", headers=emp_h)
    assert s2.status_code == 200, s2.text

    from app.models.projects import TaskTimeEntry
    async with get_sessionmaker()() as s:
        open_entries = [
            e for e in (await s.execute(select(TaskTimeEntry))).scalars().all() if e.ended_at is None
        ]
        assert len(open_entries) == 1  # only the second task is open


@pytest.mark.asyncio
async def test_timesheet_lifecycle_and_lock(client, super_admin):
    admin_h, _ = await _admin_and_employee_user(client, super_admin)
    emp = await client.post("/api/v1/employees", headers=admin_h, json={"full_name": "TS"})
    emp_id = emp.json()["id"]

    gen = await client.post(
        "/api/v1/timesheets/generate", headers=admin_h,
        json={"employee_id": emp_id, "period_start": "2026-09-01", "period_end": "2026-09-07"},
    )
    assert gen.status_code == 201, gen.text
    ts_id = gen.json()["id"]

    assert (await client.post(f"/api/v1/timesheets/{ts_id}/submit", headers=admin_h)).json()["status"] == "submitted"
    assert (await client.post(f"/api/v1/timesheets/{ts_id}/approve", headers=admin_h)).json()["status"] == "approved"
    assert (await client.post(f"/api/v1/timesheets/{ts_id}/lock", headers=admin_h)).json()["status"] == "locked"

    # locked timesheet cannot be submitted again
    resp = await client.post(f"/api/v1/timesheets/{ts_id}/submit", headers=admin_h)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_correction_approval(client, super_admin):
    admin_h, emp_h = await _admin_and_employee_user(client, super_admin)
    # employee submits a correction
    c = await client.post(
        "/api/v1/corrections", headers=emp_h,
        json={"request_type": "missed_clockin", "reason": "forgot to clock in",
              "new_value": {"actual_start": "2026-09-14T09:00:00Z"}},
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert c.json()["status"] == "pending"

    # manager/admin approves
    approve = await client.post(f"/api/v1/corrections/{cid}/approve", headers=admin_h)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_costing_requires_rate_permission(client, super_admin):
    admin_h, emp_h = await _admin_and_employee_user(client, super_admin)
    proj = await client.post("/api/v1/projects", headers=admin_h, json={"name": "P"})
    pid = proj.json()["id"]
    # employee (no rate.view) is denied
    resp = await client.get(f"/api/v1/projects/{pid}/costing", headers=emp_h)
    assert resp.status_code == 403
    # org_admin has rate.view -> allowed
    ok = await client.get(f"/api/v1/projects/{pid}/costing", headers=admin_h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["total_seconds"] == 0
