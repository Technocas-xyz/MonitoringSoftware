"""Analytics HTTP: overview, employee detail/timeline, category CRUD wiring + RBAC."""
from __future__ import annotations

import pytest

from tests.conftest import auth_header, login


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
async def test_overview_endpoint(client, super_admin):
    h = await _admin(client, super_admin)
    await client.post("/api/v1/employees", headers=h, json={"full_name": "Ahmed"})
    resp = await client.get("/api/v1/analytics/overview", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["employees"] == 1
    assert "productivity_indicator" in body


@pytest.mark.asyncio
async def test_categories_autoseed_and_list(client, super_admin):
    h = await _admin(client, super_admin)
    resp = await client.get("/api/v1/productivity/categories", headers=h)
    assert resp.status_code == 200, resp.text
    keys = {c["key"] for c in resp.json()}
    assert {"productive", "neutral", "unproductive"}.issubset(keys)


@pytest.mark.asyncio
async def test_classification_requires_permission(client, super_admin):
    h = await _admin(client, super_admin)
    # employee-role user cannot classify
    await client.post(
        "/api/v1/users", headers=h,
        json={"email": "e@acme.test", "full_name": "E", "password": "emppass123", "role_keys": ["employee"]},
    )
    emp_token = await login(client, "acme", "e@acme.test", "emppass123")
    resp = await client.post(
        "/api/v1/applications/classifications", headers=auth_header(emp_token),
        json={"target": "Code", "category_key": "productive"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_employee_timeline_endpoint(client, super_admin):
    h = await _admin(client, super_admin)
    emp = await client.post("/api/v1/employees", headers=h, json={"full_name": "T"})
    emp_id = emp.json()["id"]
    resp = await client.get(f"/api/v1/analytics/employees/{emp_id}/timeline", headers=h)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)  # empty timeline is fine
