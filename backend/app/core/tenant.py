"""Tenant context and RLS enforcement.

Row-Level Security policies filter every tenant-owned table on
`organization_id = current_setting('app.current_org')`. The GUC is transaction-local, so a
request that commits mid-handler would otherwise lose its scope for subsequent statements.

`open_tenant_session` solves this by attaching an `after_begin` listener that re-applies the
GUC at the start of *every* transaction on that session (including transactions started after
a commit). This keeps the org scope stable across multi-step, multi-transaction requests
(needed by Phase 2 shift transitions).

On non-PostgreSQL dialects (SQLite in unit tests) the GUC/RLS mechanism is unavailable, so
these operations are no-ops and isolation is validated by dedicated Postgres RLS tests.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker


def _org_literal(org_id: str) -> str:
    """Return a safe SQL string literal for an organization UUID.

    The value is parsed as a UUID first, so it cannot contain injection characters; embedding
    it as a literal avoids DBAPI paramstyle mismatches (asyncpg uses $1, not pyformat) inside
    the sync `after_begin` listener where bound-parameter passing is unreliable.
    """
    return f"'{uuid.UUID(str(org_id))}'"


def _apply_org_guc_sync(sync_session, transaction, connection, org_id: str) -> None:
    if connection.dialect.name != "postgresql":
        return
    connection.exec_driver_sql(
        f"SELECT set_config('app.current_org', {_org_literal(org_id)}, true)"
    )


async def set_current_org(session: AsyncSession, organization_id: str) -> None:
    """Set the org GUC on the current transaction (single-shot).

    Kept for flows that manage their own single transaction (login, provisioning). For
    request-scoped sessions prefer open_tenant_session().
    """
    if session.bind is not None and session.bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT set_config('app.current_org', :org, true)"),
        {"org": str(organization_id)},
    )


@asynccontextmanager
async def open_tenant_session(organization_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Yield a session that keeps `app.current_org` set across every transaction it runs."""
    session = get_sessionmaker()()

    def _listener(sync_session, transaction, connection):
        _apply_org_guc_sync(sync_session, transaction, connection, organization_id)

    # after_begin fires for each new transaction, so the GUC survives commits within a request.
    event.listen(session.sync_session, "after_begin", _listener)
    try:
        # Ensure the org is set even before the first explicit statement.
        await set_current_org(session, organization_id)
        yield session
    finally:
        event.remove(session.sync_session, "after_begin", _listener)
        await session.close()
