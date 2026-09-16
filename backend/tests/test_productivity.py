"""Productivity: indicator math, per-scope classification, rollup aggregation."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.directory import Employee
from app.models.monitoring import ApplicationEvent
from app.models.productivity import (
    ApplicationClassification,
    DailyEmployeeRollup,
    ProductivityCategory,
)
from app.productivity.defaults import NEUTRAL, PRODUCTIVE, UNPRODUCTIVE
from app.productivity.resolver import (
    CategoryWeights,
    classify_application,
    compute_indicator,
)
from app.productivity.rollups import compute_employee_rollup
from app.productivity.service import category_id_to_key, ensure_default_categories
from tests.factories import make_org_and_employee


def test_compute_indicator_default_weights():
    weights = CategoryWeights({PRODUCTIVE: 1.0, NEUTRAL: 0.5, UNPRODUCTIVE: 0.0})
    # all productive -> 100
    assert compute_indicator({PRODUCTIVE: 3600}, weights) == 100.0
    # all unproductive -> 0
    assert compute_indicator({UNPRODUCTIVE: 3600}, weights) == 0.0
    # half productive half unproductive -> 50
    assert compute_indicator({PRODUCTIVE: 1800, UNPRODUCTIVE: 1800}, weights) == 50.0
    # neutral weighted 0.5
    assert compute_indicator({NEUTRAL: 3600}, weights) == 50.0
    # empty -> 0
    assert compute_indicator({}, weights) == 0.0


@pytest.mark.asyncio
async def test_classification_per_scope_differs_by_department(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        await ensure_default_categories(s, org_id)
        await s.commit()
    async with get_sessionmaker()() as s:
        cats = {c.key: c for c in (
            await s.execute(select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id))
        ).scalars().all()}
        dept_a = uuid.uuid4()
        dept_b = uuid.uuid4()
        # Instagram: productive for dept A, unproductive for dept B (spec 26 example)
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="Instagram",
            category_id=cats[PRODUCTIVE].id, scope_type="department", scope_id=dept_a,
        ))
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="Instagram",
            category_id=cats[UNPRODUCTIVE].id, scope_type="department", scope_id=dept_b,
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        id_to_key = await category_id_to_key(s, org_id)
        a = await classify_application(s, org_id, "Instagram", None, dept_a, id_to_key)
        b = await classify_application(s, org_id, "Instagram", None, dept_b, id_to_key)
        assert a == PRODUCTIVE
        assert b == UNPRODUCTIVE


@pytest.mark.asyncio
async def test_team_scope_overrides_department(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        await ensure_default_categories(s, org_id)
        await s.commit()
    async with get_sessionmaker()() as s:
        cats = {c.key: c for c in (
            await s.execute(select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id))
        ).scalars().all()}
        dept = uuid.uuid4()
        team = uuid.uuid4()
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="Figma",
            category_id=cats[UNPRODUCTIVE].id, scope_type="department", scope_id=dept,
        ))
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="Figma",
            category_id=cats[PRODUCTIVE].id, scope_type="team", scope_id=team,
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        id_to_key = await category_id_to_key(s, org_id)
        # team-level classification wins over department
        result = await classify_application(s, org_id, "Figma", team, dept, id_to_key)
        assert result == PRODUCTIVE


@pytest.mark.asyncio
async def test_unclassified_falls_back_to_neutral(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        await ensure_default_categories(s, org_id)
        await s.commit()
        id_to_key = await category_id_to_key(s, org_id)
        result = await classify_application(s, org_id, "UnknownApp", None, None, id_to_key)
        assert result == NEUTRAL


@pytest.mark.asyncio
async def test_employee_rollup_aggregates_classified_seconds(session_factory):
    org_id, emp_id = await make_org_and_employee()
    day = now().date()
    async with get_sessionmaker()() as s:
        await ensure_default_categories(s, org_id)
        cats = {c.key: c for c in (
            await s.execute(select(ProductivityCategory).where(ProductivityCategory.organization_id == org_id))
        ).scalars().all()}
        # VS Code = productive, YouTube app = unproductive
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="Code",
            category_id=cats[PRODUCTIVE].id, scope_type="organization",
        ))
        s.add(ApplicationClassification(
            id=uuid.uuid4(), organization_id=org_id, application="YouTube",
            category_id=cats[UNPRODUCTIVE].id, scope_type="organization",
        ))
        ts = now()
        s.add(ApplicationEvent(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            application="Code", started_at=ts, duration_seconds=3000, occurred_at=ts, event_key="a1",
        ))
        s.add(ApplicationEvent(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            application="YouTube", started_at=ts, duration_seconds=1000, occurred_at=ts, event_key="a2",
        ))
        await s.commit()

    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        roll = await compute_employee_rollup(s, org_id, emp, day)
        await s.commit()
        assert roll.productive_seconds == 3000
        assert roll.unproductive_seconds == 1000
        assert roll.tracked_seconds == 4000
        # indicator = 100 * (3000*1 + 1000*0) / 4000 = 75
        assert float(roll.productivity_indicator) == 75.0
