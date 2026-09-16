"""Auth service: authentication and principal resolution.

All authorization is resolved server-side (spec 100). The principal's permission set is the
union of grants from all their role assignments; scope (team/department) is collected for
query-time narrowing.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal, RoleAssignment
from app.core.security import verify_password
from app.models.identity import Permission, Role, RolePermission, User, UserRole


async def authenticate(session: AsyncSession, org_id: uuid.UUID, email: str, password: str) -> User | None:
    result = await session.execute(
        select(User).where(User.organization_id == org_id, User.email == email)
    )
    user = result.scalar_one_or_none()
    if user is None or user.status != "active" or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def build_principal(session: AsyncSession, user: User) -> Principal:
    """Resolve permissions + scope for a user from their role assignments."""
    assignments = (
        await session.execute(select(UserRole).where(UserRole.user_id == user.id))
    ).scalars().all()

    role_ids = [a.role_id for a in assignments]
    permissions: set[str] = set()
    roles: list[RoleAssignment] = []
    scoped_team_ids: set[uuid.UUID] = set()
    scoped_department_ids: set[uuid.UUID] = set()

    if role_ids:
        role_rows = {
            r.id: r
            for r in (
                await session.execute(select(Role).where(Role.id.in_(role_ids)))
            ).scalars().all()
        }
        # permission keys granted to those roles
        perm_id_rows = (
            await session.execute(
                select(RolePermission.permission_id).where(RolePermission.role_id.in_(role_ids))
            )
        ).scalars().all()
        if perm_id_rows:
            perm_keys = (
                await session.execute(
                    select(Permission.key).where(Permission.id.in_(perm_id_rows))
                )
            ).scalars().all()
            permissions.update(perm_keys)

        for a in assignments:
            role = role_rows.get(a.role_id)
            if not role:
                continue
            roles.append(RoleAssignment(role.key, a.scope_type, a.scope_id))
            if a.scope_type == "team" and a.scope_id:
                scoped_team_ids.add(a.scope_id)
            elif a.scope_type == "department" and a.scope_id:
                scoped_department_ids.add(a.scope_id)

    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        permissions=permissions,
        roles=roles,
        scoped_team_ids=scoped_team_ids,
        scoped_department_ids=scoped_department_ids,
    )
