"""Test helpers to build tenant-scoped domain objects directly via the session factory.

These bypass HTTP to set up state for unit-style tests of the shift/attendance engine. They
run inside app.core.db's (test-swapped) session factory, so RLS is a no-op on SQLite.
"""
from __future__ import annotations

import uuid

from app.core.db import get_sessionmaker
from app.models.directory import Employee
from app.models.organization import Organization


async def make_org_and_employee(
    slug: str = "acme",
    tz: str = "UTC",
    employee_tz: str | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an org + one employee, returning (org_id, employee_id)."""
    async with get_sessionmaker()() as s:
        org = Organization(id=uuid.uuid4(), name=slug, slug=f"{slug}-{uuid.uuid4().hex[:6]}", timezone=tz)
        s.add(org)
        await s.flush()
        emp = Employee(
            id=uuid.uuid4(),
            organization_id=org.id,
            full_name="Test Employee",
            timezone=employee_tz,
            status="active",
        )
        s.add(emp)
        await s.commit()
        return org.id, emp.id
