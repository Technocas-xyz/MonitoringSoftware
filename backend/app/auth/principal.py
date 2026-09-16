"""The authenticated caller and their resolved authorization scope."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class RoleAssignment:
    role_key: str
    scope_type: str  # organization|department|team
    scope_id: uuid.UUID | None


@dataclass
class Principal:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    permissions: set[str] = field(default_factory=set)
    roles: list[RoleAssignment] = field(default_factory=list)
    # Team ids this principal is scoped to (empty => org-wide for granted perms)
    scoped_team_ids: set[uuid.UUID] = field(default_factory=set)
    scoped_department_ids: set[uuid.UUID] = field(default_factory=set)

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    @property
    def is_org_wide(self) -> bool:
        """True if any role is assigned at organization scope."""
        return any(r.scope_type == "organization" for r in self.roles)
