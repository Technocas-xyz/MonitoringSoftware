"""Policy inheritance resolution."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.models.directory import Employee
from app.models.policy import PolicyAssignment, ShiftPolicy
from app.policy.resolver import resolve_for_employee
from app.policy.defaults import DEFAULT_SHIFT_POLICY
from tests.factories import make_org_and_employee


@pytest.mark.asyncio
async def test_defaults_when_no_assignment(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        resolved = await resolve_for_employee(s, emp)
        assert resolved.shift["late_threshold_min"] == DEFAULT_SHIFT_POLICY["late_threshold_min"]


@pytest.mark.asyncio
async def test_org_policy_applies(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        policy = ShiftPolicy(
            id=uuid.uuid4(), organization_id=org_id, name="Org", late_threshold_min=5,
            allow_early_clockout=True,
        )
        s.add(policy)
        await s.flush()
        s.add(PolicyAssignment(
            id=uuid.uuid4(), organization_id=org_id, policy_kind="shift",
            policy_id=policy.id, target_type="organization", target_id=org_id,
            allow_override=True,
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        resolved = await resolve_for_employee(s, emp)
        assert resolved.shift["late_threshold_min"] == 5
        assert resolved.shift["allow_early_clockout"] is True


@pytest.mark.asyncio
async def test_employee_override_respected_when_allowed(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        org_policy = ShiftPolicy(id=uuid.uuid4(), organization_id=org_id, name="Org", late_threshold_min=5)
        emp_policy = ShiftPolicy(id=uuid.uuid4(), organization_id=org_id, name="Emp", late_threshold_min=20)
        s.add_all([org_policy, emp_policy])
        await s.flush()
        # org allows override
        s.add(PolicyAssignment(
            id=uuid.uuid4(), organization_id=org_id, policy_kind="shift",
            policy_id=org_policy.id, target_type="organization", target_id=org_id,
            allow_override=True,
        ))
        s.add(PolicyAssignment(
            id=uuid.uuid4(), organization_id=org_id, policy_kind="shift",
            policy_id=emp_policy.id, target_type="employee", target_id=emp_id,
            allow_override=False,
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        resolved = await resolve_for_employee(s, emp)
        # employee-level override applied because org allowed it
        assert resolved.shift["late_threshold_min"] == 20


@pytest.mark.asyncio
async def test_employee_override_blocked_when_not_allowed(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        org_policy = ShiftPolicy(id=uuid.uuid4(), organization_id=org_id, name="Org", late_threshold_min=5)
        emp_policy = ShiftPolicy(id=uuid.uuid4(), organization_id=org_id, name="Emp", late_threshold_min=20)
        s.add_all([org_policy, emp_policy])
        await s.flush()
        # org does NOT allow override
        s.add(PolicyAssignment(
            id=uuid.uuid4(), organization_id=org_id, policy_kind="shift",
            policy_id=org_policy.id, target_type="organization", target_id=org_id,
            allow_override=False,
        ))
        s.add(PolicyAssignment(
            id=uuid.uuid4(), organization_id=org_id, policy_kind="shift",
            policy_id=emp_policy.id, target_type="employee", target_id=emp_id,
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        resolved = await resolve_for_employee(s, emp)
        # employee override blocked -> org value stands
        assert resolved.shift["late_threshold_min"] == 5
