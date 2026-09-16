"""PostgreSQL Row-Level Security isolation tests.

Skipped unless TEST_DATABASE_URL points at a PostgreSQL instance, because RLS is a
Postgres-layer feature. Run with e.g.:
    TEST_DATABASE_URL=postgresql+asyncpg://rwm:rwm@localhost:5432/rwm_test pytest tests/test_rls_postgres.py

Note: these tests assume the schema is created via Alembic migrations (which install the RLS
policies). Base.metadata.create_all does NOT create the policies, so a Postgres run should
apply migrations first.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenant import set_current_org
from app.models.identity import User
from app.models.organization import Organization

pytestmark = pytest.mark.skipif(
    "postgresql" not in os.getenv("TEST_DATABASE_URL", ""),
    reason="RLS isolation requires a PostgreSQL TEST_DATABASE_URL",
)


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads():
    url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()

    # Seed two orgs + a user each, bypassing RLS as table owner via a superuser session.
    async with factory() as s:
        s.add(Organization(id=org_a, name="A", slug=f"a-{org_a.hex[:8]}"))
        s.add(Organization(id=org_b, name="B", slug=f"b-{org_b.hex[:8]}"))
        await s.flush()
        await set_current_org(s, str(org_a))
        s.add(User(id=uuid.uuid4(), organization_id=org_a, email="a@a.test", full_name="A"))
        await s.commit()

    # A session scoped to org_b must not see org_a's users.
    async with factory() as s:
        await set_current_org(s, str(org_b))
        rows = (await s.execute(select(User))).scalars().all()
        assert all(u.organization_id == org_b for u in rows)
        assert not any(u.email == "a@a.test" for u in rows)

    await engine.dispose()


@pytest.mark.asyncio
async def test_open_tenant_session_reapplies_guc_across_commits():
    """Regression: the after_begin listener must set app.current_org via a statement the
    asyncpg driver accepts (paramstyle mismatch previously broke this), and must re-apply the
    GUC after a mid-session commit so RLS stays scoped."""
    import app.core.db as db_module
    from app.core.tenant import open_tenant_session

    url = os.environ["TEST_DATABASE_URL"]
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    original = db_module.get_sessionmaker()
    db_module.set_sessionmaker(factory)

    org = uuid.uuid4()
    try:
        # Seed org + a user under RLS.
        async with open_tenant_session(str(org)) as s:
            s.add(Organization(id=org, name="C", slug=f"c-{org.hex[:8]}"))
            await s.flush()
            s.add(User(id=uuid.uuid4(), organization_id=org, email="c@c.test", full_name="C"))
            await s.commit()  # first transaction ends here

            # New transaction begins on next statement; GUC must be re-applied by the listener.
            got = (await s.execute(text("SELECT current_setting('app.current_org', true)"))).scalar()
            assert got == str(org)

            rows = (await s.execute(select(User))).scalars().all()
            assert any(u.email == "c@c.test" for u in rows)
    finally:
        db_module.set_sessionmaker(original)
        await engine.dispose()
