"""Database engine, session, and Base.

Tenant isolation (spec 43): every tenant-scoped request runs inside a transaction where
`app.current_org` is set, so PostgreSQL Row-Level Security filters all queries to the
caller's organization. See app/core/tenant.py for how the GUC is set per request.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the active session factory.

    Callers should use this (not the module-level name) so tests can swap the factory at
    runtime by calling set_sessionmaker().
    """
    return SessionFactory


def set_sessionmaker(factory: async_sessionmaker[AsyncSession]) -> None:
    """Override the active session factory (used by tests)."""
    global SessionFactory
    SessionFactory = factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a raw session (no tenant scope).

    Used for auth/login where the org is not yet known. Tenant-scoped routes should use
    `app.core.deps.get_tenant_session` instead.
    """
    async with get_sessionmaker()() as session:
        yield session
