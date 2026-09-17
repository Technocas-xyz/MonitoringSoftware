"""Local/demo bootstrap on SQLite (no Postgres/Alembic needed).

Creates all tables from SQLAlchemy metadata (RLS is Postgres-only and simply absent here),
then seeds a platform super admin. For real deployments use Alembic migrations on PostgreSQL.

Usage:
    set DATABASE_URL=sqlite+aiosqlite:///./dev.db
    python dev_sqlite_init.py <email> <password>
"""
from __future__ import annotations

import asyncio
import sys

from app.core.db import Base, engine
import app.models  # noqa: F401  register all tables
from app.core.bootstrap import bootstrap


async def main(email: str, password: str) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bootstrap(email, password)
    print("SQLite dev DB initialized + admin bootstrapped.")


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "root@platform.local"
    password = sys.argv[2] if len(sys.argv) > 2 else "devpassword123"
    asyncio.run(main(email, password))
