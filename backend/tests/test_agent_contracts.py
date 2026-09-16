"""Server-side agent contract tests: enroll -> approve -> token -> signed agent calls."""
from __future__ import annotations

import time

import pytest

from app.core.security import sign_request
from tests.conftest import auth_header, login


async def _setup_org_employee_user(client, super_admin):
    """Provision org, create an employee linked to a user with the employee role."""
    root = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    await client.post(
        "/api/v1/organizations", headers=auth_header(root),
        json={
            "name": "Acme", "slug": "acme", "timezone": "UTC",
            "admin_email": "admin@acme.test", "admin_password": "acmepass123",
            "admin_full_name": "Admin",
        },
    )
    admin = await login(client, "acme", "admin@acme.test", "acmepass123")
    h = auth_header(admin)

    # employee user
    u = await client.post(
        "/api/v1/users", headers=h,
        json={"email": "emp@acme.test", "full_name": "Emp", "password": "emppass123", "role_keys": ["employee"]},
    )
    user_id = u.json()["id"]
    # employee linked to that user
    e = await client.post(
        "/api/v1/employees", headers=h, json={"full_name": "Emp", "user_id": user_id},
    )
    assert e.status_code == 201, e.text
    emp_token = await login(client, "acme", "emp@acme.test", "emppass123")
    return h, emp_token


@pytest.mark.asyncio
async def test_enroll_approve_token_and_signed_call(client, super_admin):
    admin_h, emp_token = await _setup_org_employee_user(client, super_admin)

    # 1. employee enrolls device
    enroll = await client.post(
        "/api/v1/auth/agent/enroll", headers=auth_header(emp_token),
        json={"hostname": "PC-1", "os": "windows", "agent_version": "1.0.0"},
    )
    assert enroll.status_code == 201, enroll.text
    device_id = enroll.json()["device_id"]

    # 2. admin approves -> receives signing secret once
    approve = await client.post(f"/api/v1/devices/{device_id}/approve", headers=admin_h)
    assert approve.status_code == 200, approve.text
    secret = approve.json()["signing_secret"]
    assert secret

    # 3. exchange signing proof for a device token
    ts = str(int(time.time()))
    proof = sign_request(secret, "TOKEN", "/auth/agent/token", device_id, ts)
    tok = await client.post(
        "/api/v1/auth/agent/token",
        json={"organization_slug": "acme", "device_id": device_id, "timestamp": ts, "signature": proof},
    )
    assert tok.status_code == 200, tok.text
    device_token = tok.json()["device_token"]

    # 4. signed agent call: GET /agent/shift/current
    path = "/api/v1/agent/shift/current"
    ts2 = str(int(time.time()))
    sig = sign_request(secret, "GET", path, "", ts2)
    resp = await client.get(
        path,
        headers={
            "Authorization": f"Bearer {device_token}",
            "X-Signature": sig,
            "X-Timestamp": ts2,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "server_time" in body
    assert body["shift_id"] is None  # no active shift yet


@pytest.mark.asyncio
async def test_agent_call_rejected_without_signature(client, super_admin):
    admin_h, emp_token = await _setup_org_employee_user(client, super_admin)
    enroll = await client.post(
        "/api/v1/auth/agent/enroll", headers=auth_header(emp_token), json={"hostname": "PC-2"}
    )
    device_id = enroll.json()["device_id"]
    secret = (await client.post(f"/api/v1/devices/{device_id}/approve", headers=admin_h)).json()["signing_secret"]
    ts = str(int(time.time()))
    proof = sign_request(secret, "TOKEN", "/auth/agent/token", device_id, ts)
    device_token = (
        await client.post(
            "/api/v1/auth/agent/token",
            json={"organization_slug": "acme", "device_id": device_id, "timestamp": ts, "signature": proof},
        )
    ).json()["device_token"]

    # missing X-Signature/X-Timestamp -> 401
    resp = await client.get(
        "/api/v1/agent/shift/current", headers={"Authorization": f"Bearer {device_token}"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_denied_for_unapproved_device(client, super_admin):
    admin_h, emp_token = await _setup_org_employee_user(client, super_admin)
    enroll = await client.post(
        "/api/v1/auth/agent/enroll", headers=auth_header(emp_token), json={"hostname": "PC-3"}
    )
    device_id = enroll.json()["device_id"]
    # not approved -> no secret; token request must fail
    ts = str(int(time.time()))
    resp = await client.post(
        "/api/v1/auth/agent/token",
        json={"organization_slug": "acme", "device_id": device_id, "timestamp": ts, "signature": "deadbeef"},
    )
    assert resp.status_code == 403
