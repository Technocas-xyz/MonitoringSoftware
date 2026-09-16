"""Phase 7: alert engine, notification rendering, report CSV, webhook emit/signature."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.alerts.engine import evaluate_org
from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.alerts import Alert, AlertRule, Notification, Webhook, WebhookDelivery
from app.models.shifts import Attendance
from app.notifications.service import render_template
from app.reports import builders, exporters
from app.webhooks.service import emit, sign_payload
from tests.factories import make_org_and_employee


def test_render_template_substitutes_placeholders():
    body = "Employee {{employee_name}} was {{late_minutes}} min late"
    out = render_template(body, {"employee_name": "Ahmed", "late_minutes": 7})
    assert out == "Employee Ahmed was 7 min late"
    # unknown placeholder becomes empty
    assert render_template("Hi {{missing}}!", {}) == "Hi !"


def test_sign_payload_is_deterministic():
    a = sign_payload("secret", '{"x":1}')
    b = sign_payload("secret", '{"x":1}')
    c = sign_payload("secret", '{"x":2}')
    assert a == b
    assert a != c
    assert len(a) == 64  # sha256 hex


async def _attendance(session, org_id, emp_id, **kw):
    att = Attendance(
        id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id,
        work_date=now().date(), status=kw.get("status", "LATE"),
        worked_seconds=0, break_seconds=0, idle_seconds=kw.get("idle_seconds", 0),
        late_seconds=kw.get("late_seconds", 0), early_leave_seconds=kw.get("early_leave_seconds", 0),
        overtime_seconds=0, computed_at=now(),
    )
    session.add(att)
    await session.flush()


@pytest.mark.asyncio
async def test_late_alert_fires_once(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        s.add(AlertRule(
            id=uuid.uuid4(), organization_id=org_id, key="late_arrival", enabled=True,
            severity="warning", params={"threshold_seconds": 300}, channels=["in_app"],
        ))
        await _attendance(s, org_id, emp_id, status="LATE", late_seconds=600)
        await s.commit()

    async with get_sessionmaker()() as s:
        n1 = await evaluate_org(s, org_id, now().date())
        await s.commit()
        assert n1 == 1
    # Re-evaluation is idempotent (dedup) — no second alert.
    async with get_sessionmaker()() as s:
        n2 = await evaluate_org(s, org_id, now().date())
        await s.commit()
        assert n2 == 0
        alerts = (await s.execute(select(Alert))).scalars().all()
        assert len(alerts) == 1
        # a notification was dispatched
        notes = (await s.execute(select(Notification))).scalars().all()
        assert len(notes) == 1


@pytest.mark.asyncio
async def test_late_alert_not_fired_below_threshold(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        s.add(AlertRule(
            id=uuid.uuid4(), organization_id=org_id, key="late_arrival", enabled=True,
            params={"threshold_seconds": 900}, channels=["in_app"],
        ))
        await _attendance(s, org_id, emp_id, status="LATE", late_seconds=600)  # below 900
        await s.commit()
    async with get_sessionmaker()() as s:
        n = await evaluate_org(s, org_id, now().date())
        await s.commit()
        assert n == 0


@pytest.mark.asyncio
async def test_attendance_report_csv(session_factory):
    org_id, emp_id = await make_org_and_employee()
    from datetime import date
    async with get_sessionmaker()() as s:
        await _attendance(s, org_id, emp_id, status="PRESENT", late_seconds=0)
        await s.commit()
    async with get_sessionmaker()() as s:
        data = await builders.build(s, "attendance", org_id, date(2000, 1, 1), date(2100, 1, 1))
        content, ctype, ext = exporters.export(data, "csv")
        assert ext == "csv"
        text = content.decode("utf-8")
        assert "Employee,Date,Status" in text
        assert "PRESENT" in text


@pytest.mark.asyncio
async def test_webhook_emit_queues_only_subscribed(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        s.add(Webhook(
            id=uuid.uuid4(), organization_id=org_id, url="https://example.test/hook",
            secret="s", events=["shift.started"], enabled=True,
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        # subscribed event queues
        q1 = await emit(s, org_id, "shift.started", {"x": 1})
        # unsubscribed event does not
        q2 = await emit(s, org_id, "shift.ended", {"x": 1})
        await s.commit()
        assert q1 == 1
        assert q2 == 0
        deliveries = (await s.execute(select(WebhookDelivery))).scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].event == "shift.started"
