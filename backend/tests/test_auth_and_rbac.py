"""Auth + RBAC enforcement tests."""
from __future__ import annotations

import pytest

from tests.conftest import auth_header, login


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_super_admin_login_and_me(client, super_admin):
    token = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    resp = await client.get("/api/v1/auth/me", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == super_admin["email"]
    assert "platform.admin" in body["permissions"]
    assert "super_admin" in body["roles"]


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client, super_admin):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": super_admin["slug"], "email": super_admin["email"], "password": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_is_rejected(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_rotates_tokens(client, super_admin):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": super_admin["slug"], "email": super_admin["email"], "password": super_admin["password"]},
    )
    refresh = resp.json()["refresh_token"]
    r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    assert "access_token" in r2.json()


@pytest.mark.asyncio
async def test_permission_enforced_for_provisioning(client, super_admin):
    """Provision an org + org admin, then confirm the org admin lacks platform.admin."""
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

    # org admin logs in and tries to provision another org -> forbidden
    admin_token = await login(client, "acme", "admin@acme.test", "acmepass123")
    forbidden = await client.post(
        "/api/v1/organizations",
        headers=auth_header(admin_token),
        json={
            "name": "Beta",
            "slug": "beta",
            "timezone": "UTC",
            "admin_email": "x@beta.test",
            "admin_password": "betapass123",
            "admin_full_name": "B",
        },
    )
    assert forbidden.status_code == 403
