"""Test fixtures.

Most tests run against an in-memory SQLite database to validate application behavior
(auth, RBAC, scope narrowing, audit). PostgreSQL Row-Level Security is a database-layer
feature covered separately in test_rls_postgres.py (skipped without a Postgres URL).

The app resolves its session factory through app.core.db.get_sessionmaker(), so tests swap
it via set_sessionmaker() to point at the test database. set_current_org is a no-op on
non-Postgres dialects, so the app code path runs unchanged on SQLite.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.db as db_module
from app.core.db import Base
import app.models  # noqa: F401  register metadata

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original = db_module.get_sessionmaker()
    db_module.set_sessionmaker(factory)
    yield factory
    db_module.set_sessionmaker(original)


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def super_admin(session_factory):
    """Bootstrap a platform super admin and return login context."""
    from app.core.bootstrap import PLATFORM_SLUG, bootstrap

    await bootstrap("root@platform.test", "rootpass123")
    return {"slug": PLATFORM_SLUG, "email": "root@platform.test", "password": "rootpass123"}


async def login(client: AsyncClient, slug: str, email: str, password: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
