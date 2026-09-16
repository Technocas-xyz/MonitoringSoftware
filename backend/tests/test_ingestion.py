"""Ingestion service: idempotency, policy-based field dropping, shift binding."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.ingestion.service import ingest_batch
from app.models.monitoring import ApplicationEvent, WebsiteEvent
from app.models.shifts import WORKING, Shift
from tests.factories import make_org_and_employee


async def _active_shift(org_id, emp_id, monitoring: dict):
    async with get_sessionmaker()() as s:
        shift = Shift(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, state=WORKING,
            timezone="UTC", policy_snapshot={"monitoring": monitoring}, version=1,
        )
        s.add(shift)
        await s.commit()
        return shift.id


@pytest.mark.asyncio
async def test_application_event_persisted_and_bound_to_shift(session_factory):
    org_id, emp_id = await make_org_and_employee()
    shift_id = await _active_shift(org_id, emp_id, {"monitor_applications": True})
    dev = uuid.uuid4()
    async with get_sessionmaker()() as s:
        res = await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=dev,
            events=[{
                "event_id": "e1", "type": "APPLICATION_ACTIVITY",
                "payload": {"application": "Code", "window_title": "main.py", "duration": 600},
            }],
        )
        await s.commit()
        assert res.accepted == 1
        row = (await s.execute(select(ApplicationEvent))).scalar_one()
        assert row.application == "Code"
        assert row.shift_id == shift_id
        assert row.window_title == "main.py"  # allowed by policy


@pytest.mark.asyncio
async def test_window_title_dropped_when_apps_not_monitored(session_factory):
    org_id, emp_id = await make_org_and_employee()
    await _active_shift(org_id, emp_id, {"monitor_applications": False})
    async with get_sessionmaker()() as s:
        await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            events=[{
                "event_id": "e2", "type": "APPLICATION_ACTIVITY",
                "payload": {"application": "Code", "window_title": "secret.py"},
            }],
        )
        await s.commit()
        row = (await s.execute(select(ApplicationEvent))).scalar_one()
        assert row.window_title is None  # dropped for privacy


@pytest.mark.asyncio
async def test_website_url_dropped_unless_full_url_mode(session_factory):
    org_id, emp_id = await make_org_and_employee()
    await _active_shift(org_id, emp_id, {"website_mode": "domain"})
    async with get_sessionmaker()() as s:
        await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            events=[{
                "event_id": "w1", "type": "WEBSITE_ACTIVITY",
                "payload": {"domain": "github.com", "url": "https://github.com/private/repo"},
            }],
        )
        await s.commit()
        row = (await s.execute(select(WebsiteEvent))).scalar_one()
        assert row.domain == "github.com"
        assert row.url is None  # domain-only mode drops URL


@pytest.mark.asyncio
async def test_duplicate_event_id_is_deduped(session_factory):
    org_id, emp_id = await make_org_and_employee()
    await _active_shift(org_id, emp_id, {"monitor_applications": True})
    async with get_sessionmaker()() as s:
        r1 = await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            events=[{"event_id": "dup", "type": "APPLICATION_ACTIVITY", "payload": {"application": "A"}}],
        )
        await s.commit()
        assert r1.accepted == 1
    async with get_sessionmaker()() as s:
        r2 = await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            events=[{"event_id": "dup", "type": "APPLICATION_ACTIVITY", "payload": {"application": "A"}}],
        )
        await s.commit()
        assert r2.duplicates == 1
        assert r2.accepted == 0
        count = len((await s.execute(select(ApplicationEvent))).scalars().all())
        assert count == 1


@pytest.mark.asyncio
async def test_unknown_type_rejected(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        res = await ingest_batch(
            s, organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            events=[{"event_id": "x", "type": "BOGUS", "payload": {}}],
        )
        await s.commit()
        assert res.rejected == 1
        assert res.accepted == 0
