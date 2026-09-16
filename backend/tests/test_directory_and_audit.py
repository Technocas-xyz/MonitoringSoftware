"""Directory CRUD, rate-gating, scope-narrowing, and audit trail tests."""
from __future__ import annotations

import pytest

from tests.conftest import auth_header, login


async def _provision_acme(client, super_admin):
    token = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    resp = await client.post(
        "/api/v1/organizations",
        headers=auth_header(token),
        json={
            "name": "Acme",
            "slug": "acme",
            "timezone": "UTC",
            "admin_email": "admin@acme.test",
            "admin_password": "acmepass123",
            "admin_full_name": "Acme Admin",
        },
    )
    assert resp.status_code == 201, resp.text
    return await login(client, "acme", "admin@acme.test", "acmepass123")


@pytest.mark.asyncio
async def test_full_directory_flow(client, super_admin):
    admin = await _provision_acme(client, super_admin)
    h = auth_header(admin)

    dept = await client.post("/api/v1/departments", headers=h, json={"name": "Engineering"})
    assert dept.status_code == 201, dept.text
    dept_id = dept.json()["id"]

    team = await client.post(
        "/api/v1/teams", headers=h, json={"name": "Platform", "department_id": dept_id}
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]

    emp = await client.post(
        "/api/v1/employees",
        headers=h,
        json={"full_name": "Ahmed", "employee_code": "E-1", "team_id": team_id},
    )
    assert emp.status_code == 201, emp.text

    listing = await client.get("/api/v1/employees", headers=h)
    assert listing.status_code == 200
    assert any(e["full_name"] == "Ahmed" for e in listing.json())


@pytest.mark.asyncio
async def test_rate_field_is_gated(client, super_admin):
    """org_admin has rate.view but not rate.manage; setting a rate must be forbidden."""
    admin = await _provision_acme(client, super_admin)
    h = auth_header(admin)

    # org_admin grant set includes rate.view but not rate.manage (see rbac.ROLE_GRANTS)
    resp = await client.post(
        "/api/v1/employees",
        headers=h,
        json={"full_name": "Rated", "hourly_rate": 50.0},
    )
    assert resp.status_code == 403
    assert "rate.manage" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_audit_trail_records_actions(client, super_admin):
    admin = await _provision_acme(client, super_admin)
    h = auth_header(admin)
    await client.post("/api/v1/departments", headers=h, json={"name": "Sales"})

    logs = await client.get("/api/v1/audit-logs", headers=h)
    assert logs.status_code == 200
    actions = {row["action"] for row in logs.json()}
    # provisioning login + department creation should be present
    assert "department.create" in actions


@pytest.mark.asyncio
async def test_devices_lifecycle(client, super_admin):
    admin = await _provision_acme(client, super_admin)
    h = auth_header(admin)
    emp = await client.post("/api/v1/employees", headers=h, json={"full_name": "Dev Owner"})
    emp_id = emp.json()["id"]

    enroll = await client.post(
        "/api/v1/devices", headers=h, json={"employee_id": emp_id, "hostname": "PC-1", "os": "windows"}
    )
    assert enroll.status_code == 201, enroll.text
    device_id = enroll.json()["id"]
    assert enroll.json()["status"] == "pending"

    approve = await client.post(f"/api/v1/devices/{device_id}/approve", headers=h)
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    revoke = await client.post(f"/api/v1/devices/{device_id}/revoke", headers=h)
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"
