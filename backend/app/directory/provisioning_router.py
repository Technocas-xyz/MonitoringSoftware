"""Organization provisioning (platform.admin).

Creates an organization, seeds its RBAC (via global system roles), and creates the first
org admin user with the org_admin role assigned at organization scope.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.principal import Principal
from app.core.db import get_sessionmaker
from app.core.deps import require_permission
from app.core.rbac import ORG_ADMIN
from app.core.security import hash_password
from app.core.seed import seed_permissions_and_roles
from app.core.tenant import set_current_org
from app.directory.schemas import (
    OrganizationOut,
    ProvisionOrgRequest,
    ProvisionOrgResponse,
)
from app.models.identity import Role, User, UserRole
from app.models.organization import Organization

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=ProvisionOrgResponse, status_code=201)
async def provision_organization(
    payload: ProvisionOrgRequest,
    principal: Principal = Depends(require_permission("platform.admin")),
):
    async with get_sessionmaker()() as session:
        # Uniqueness check for slug
        existing = (
            await session.execute(select(Organization).where(Organization.slug == payload.slug))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="organization slug already exists")

        # Ensure global permissions + system roles exist
        await seed_permissions_and_roles(session)

        org = Organization(
            id=uuid.uuid4(),
            name=payload.name,
            slug=payload.slug,
            timezone=payload.timezone,
        )
        session.add(org)
        await session.flush()

        # RLS applies to users; scope the session to this org before inserting.
        await set_current_org(session, str(org.id))

        admin = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=payload.admin_email,
            password_hash=hash_password(payload.admin_password),
            full_name=payload.admin_full_name,
        )
        session.add(admin)
        await session.flush()

        org_admin_role = (
            await session.execute(
                select(Role).where(Role.organization_id.is_(None), Role.key == ORG_ADMIN)
            )
        ).scalar_one()
        session.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=admin.id,
                role_id=org_admin_role.id,
                scope_type="organization",
                scope_id=None,
            )
        )

        await audit.record(
            session,
            action="org.provision",
            organization_id=org.id,
            actor_user_id=principal.user_id,
            target_type="organization",
            target_id=org.id,
            new_value={"slug": org.slug, "name": org.name},
        )
        await session.commit()

        return ProvisionOrgResponse(
            organization=OrganizationOut.model_validate(org),
            admin_user_id=admin.id,
        )
