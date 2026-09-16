"""One-time platform bootstrap.

Solves the chicken-and-egg: provisioning organizations requires platform.admin, but no user
exists yet. This creates a dedicated platform organization + a super_admin user holding the
super_admin role (which includes platform.admin).

Run:  python -m app.core.bootstrap <email> <password>
Idempotent: re-running updates the password of the existing bootstrap admin.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.rbac import SUPER_ADMIN
from app.core.security import hash_password
from app.core.seed import seed_permissions_and_roles
from app.core.tenant import set_current_org
from app.models.identity import Role, User, UserRole
from app.models.organization import Organization

PLATFORM_SLUG = "platform"


async def bootstrap(email: str, password: str) -> None:
    async with get_sessionmaker()() as session:
        await seed_permissions_and_roles(session)

        org = (
            await session.execute(select(Organization).where(Organization.slug == PLATFORM_SLUG))
        ).scalar_one_or_none()
        if org is None:
            org = Organization(
                id=uuid.uuid4(), name="Platform", slug=PLATFORM_SLUG, timezone="UTC"
            )
            session.add(org)
            await session.flush()

        await set_current_org(session, str(org.id))

        user = (
            await session.execute(
                select(User).where(User.organization_id == org.id, User.email == email)
            )
        ).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                organization_id=org.id,
                email=email,
                full_name="Platform Super Admin",
                password_hash=hash_password(password),
            )
            session.add(user)
            await session.flush()
        else:
            user.password_hash = hash_password(password)

        super_role = (
            await session.execute(
                select(Role).where(Role.organization_id.is_(None), Role.key == SUPER_ADMIN)
            )
        ).scalar_one()

        existing = (
            await session.execute(
                select(UserRole).where(
                    UserRole.user_id == user.id, UserRole.role_id == super_role.id
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                UserRole(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    role_id=super_role.id,
                    scope_type="organization",
                    scope_id=None,
                )
            )

        await session.commit()
        print(f"Bootstrap complete. Org slug '{PLATFORM_SLUG}', super admin '{email}'.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m app.core.bootstrap <email> <password>")
        raise SystemExit(1)
    asyncio.run(bootstrap(sys.argv[1], sys.argv[2]))
