"""Idempotent seeding of permissions and system roles.

Seeds the global permission catalog and the platform-level system roles with their default
grants (from app.core.rbac). Org-scoped role copies can be created per organization, but the
platform system roles (organization_id = NULL) are the canonical templates and are what the
provisioning flow assigns for a first org admin.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import PERMISSIONS, ROLE_GRANTS, SYSTEM_ROLES
from app.models.identity import Permission, Role, RolePermission


async def seed_permissions_and_roles(session: AsyncSession) -> None:
    # Permissions
    existing_perms = {
        p.key: p for p in (await session.execute(select(Permission))).scalars().all()
    }
    for key, description in PERMISSIONS.items():
        if key not in existing_perms:
            perm = Permission(id=uuid.uuid4(), key=key, description=description)
            session.add(perm)
            existing_perms[key] = perm
    await session.flush()

    # System roles (platform-level: organization_id = NULL)
    existing_roles = {
        r.key: r
        for r in (
            await session.execute(select(Role).where(Role.organization_id.is_(None)))
        ).scalars().all()
    }
    for key, name in SYSTEM_ROLES.items():
        role = existing_roles.get(key)
        if role is None:
            role = Role(id=uuid.uuid4(), organization_id=None, key=key, name=name, is_system=True)
            session.add(role)
            await session.flush()
            existing_roles[key] = role

        # Sync grants
        current = {
            rp.permission_id
            for rp in (
                await session.execute(
                    select(RolePermission).where(RolePermission.role_id == role.id)
                )
            ).scalars().all()
        }
        for perm_key in ROLE_GRANTS.get(key, []):
            perm = existing_perms.get(perm_key)
            if perm and perm.id not in current:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await session.flush()
