"""HTTP-level Phase 2 smoke tests: policy + schedule endpoints wire up and enforce RBAC."""
from __future__ import annotations

import pytest

from tests.conftest import auth_header, login


async def _provision_and_admin(client, super_admin):
    token = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    resp = await client.post(
        "/api/v1/organizations",
        headers=auth_header(token),
        json={
            "name": "Acme", "slug": "acme", "timezone": "UTC",
            "admin_email": "admin@acme.test", "admin_password": "acmepass123",
            "admin_full_name": "Acme Admin",
        },
    )
    assert resp.status_code == 201, resp.text
    return await login(client, "acme", "admin@acme.test", "acmepass123")


@pytest.mark.asyncio
async def test_shift_policy_crud_and_preview(client, super_admin):
    admin = await _provision_and_admin(client, super_admin)
    h = auth_header(admin)

    # create an employee
    emp = await client.post("/api/v1/employees", headers=h, json={"full_name": "Ahmed"})
    assert emp.status_code == 201, emp.text
    emp_id = emp.json()["id"]

    # create + assign a shift policy at org scope
    pol = await client.post(
        "/api/v1/shift-policies", headers=h,
        json={"name": "Standard", "late_threshold_min": 10, "allow_early_clockout": True},
    )
    assert pol.status_code == 201, pol.text
    pol_id = pol.json()["id"]

    # need the org id: read /me
    me = (await client.get("/api/v1/auth/me", headers=h)).json()
    org_id = me["organization_id"]

    assign = await client.post(
        "/api/v1/policies/assign", headers=h,
        json={
            "policy_kind": "shift", "policy_id": pol_id,
            "target_type": "organization", "target_id": org_id, "allow_override": True,
        },
    )
    assert assign.status_code == 201, assign.text

    # preview resolves the org policy for the employee
    preview = await client.get(f"/api/v1/policies/preview?employee_id={emp_id}", headers=h)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["shift"]["late_threshold_min"] == 10
    assert body["shift"]["allow_early_clockout"] is True
    assert any("Late after: 10 min" in line for line in body["summary"])


@pytest.mark.asyncio
async def test_schedule_occurrences_endpoint(client, super_admin):
    admin = await _provision_and_admin(client, super_admin)
    h = auth_header(admin)

    emp = await client.post("/api/v1/employees", headers=h, json={"full_name": "Sara"})
    emp_id = emp.json()["id"]

    sched = await client.post(
        "/api/v1/schedules", headers=h,
        json={"name": "9-6", "type": "fixed", "definition": {"days": {"mon": ["09:00", "18:00"]}}},
    )
    assert sched.status_code == 201, sched.text
    sched_id = sched.json()["id"]

    assign = await client.post(
        f"/api/v1/schedules/{sched_id}/assign", headers=h,
        json={
            "schedule_id": sched_id, "target_type": "employee",
            "target_id": emp_id, "effective_from": "2026-01-01",
        },
    )
    assert assign.status_code == 201, assign.text

    # Monday 2026-09-14
    occ = await client.get(
        f"/api/v1/schedules/occurrences?employee_id={emp_id}&day=2026-09-14", headers=h
    )
    assert occ.status_code == 200, occ.text
    data = occ.json()
    assert data["schedule_id"] == sched_id
    assert len(data["occurrences"]) == 1


@pytest.mark.asyncio
async def test_employee_cannot_manage_policies(client, super_admin):
    admin = await _provision_and_admin(client, super_admin)
    h = auth_header(admin)
    # create a plain employee user with only the employee role
    u = await client.post(
        "/api/v1/users", headers=h,
        json={"email": "e@acme.test", "full_name": "E", "password": "emppass123", "role_keys": ["employee"]},
    )
    assert u.status_code == 201, u.text
    emp_token = await login(client, "acme", "e@acme.test", "emppass123")
    resp = await client.post(
        "/api/v1/shift-policies", headers=auth_header(emp_token), json={"name": "X"}
    )
    assert resp.status_code == 403
