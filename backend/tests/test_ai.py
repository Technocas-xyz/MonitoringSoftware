"""Phase 8 AI: scope enforcement, summary content, anomaly detection, NL answer, provider."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.ai import service as ai_service
from app.ai.provider import TemplateProvider
from app.ai.scope import ScopeDenied, require_employee_in_scope
from app.auth.principal import Principal
from app.core.db import get_sessionmaker
from app.core.time_authority import now
from app.models.directory import Employee
from app.models.monitoring import ApplicationEvent
from app.models.productivity import DailyEmployeeRollup
from tests.conftest import auth_header, login
from tests.factories import make_org_and_employee


def _principal(org_id, user_id, *, org_wide=False, teams=None) -> Principal:
    from app.auth.principal import RoleAssignment
    roles = [RoleAssignment("org_admin" if org_wide else "manager",
                            "organization" if org_wide else "team",
                            None if org_wide else (list(teams)[0] if teams else None))]
    return Principal(
        user_id=user_id, organization_id=org_id, email="x@test",
        permissions={"ai.use"}, roles=roles,
        scoped_team_ids=set(teams or set()), scoped_department_ids=set(),
    )


# ---- provider ----
def test_template_provider_summary_mentions_hours_and_apps():
    p = TemplateProvider()
    text = p.summarize({
        "subject": "Ahmed", "worked_seconds": 7 * 3600 + 42 * 60, "idle_seconds": 37 * 60,
        "indicator": 82.0, "top_applications": [{"name": "Code"}, {"name": "Chrome"}],
    })
    assert "Ahmed worked 7h 42m" in text
    assert "Code" in text
    assert "82.0%" in text


def test_template_provider_anomaly_none():
    p = TemplateProvider()
    assert "No unusual" in p.explain_anomaly({"anomalous": False})
    flagged = p.explain_anomaly({"anomalous": True, "changes": [
        {"name": "YouTube", "today_pct": 41, "baseline_pct": 5, "direction": "rose"}]})
    assert "Unusual activity pattern detected" in flagged
    assert "YouTube" in flagged


# ---- scope guard ----
@pytest.mark.asyncio
async def test_scope_denies_out_of_team_employee(session_factory):
    org_id, emp_id = await make_org_and_employee()
    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        emp.team_id = uuid.uuid4()  # a team the manager does NOT manage
        await s.commit()
    # manager scoped to a different team
    manager = _principal(org_id, uuid.uuid4(), teams={uuid.uuid4()})
    async with get_sessionmaker()() as s:
        with pytest.raises(ScopeDenied):
            await require_employee_in_scope(s, manager, emp_id)


@pytest.mark.asyncio
async def test_scope_allows_org_wide(session_factory):
    org_id, emp_id = await make_org_and_employee()
    admin = _principal(org_id, uuid.uuid4(), org_wide=True)
    async with get_sessionmaker()() as s:
        emp = await require_employee_in_scope(s, admin, emp_id)
        assert emp.id == emp_id


# ---- summary + anomaly ----
@pytest.mark.asyncio
async def test_employee_summary_from_rollup(session_factory):
    org_id, emp_id = await make_org_and_employee()
    day = now().date()
    async with get_sessionmaker()() as s:
        s.add(DailyEmployeeRollup(
            organization_id=org_id, employee_id=emp_id, work_date=day,
            tracked_seconds=27000, productive_seconds=20000, neutral_seconds=5000,
            unproductive_seconds=2000, idle_seconds=1200, worked_seconds=27720,
            productivity_indicator=82.0,
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        result = await ai_service.employee_summary(s, org_id, emp, day)
        assert result["facts"]["indicator"] == 82.0
        assert "worked" in result["text"].lower()


@pytest.mark.asyncio
async def test_anomaly_detects_spike(session_factory):
    org_id, emp_id = await make_org_and_employee()
    day = now().date()
    async with get_sessionmaker()() as s:
        # baseline (7 days ago): all Code
        base_ts = now() - timedelta(days=7)
        s.add(ApplicationEvent(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            application="Code", started_at=base_ts, duration_seconds=3600, occurred_at=base_ts, event_key="b1",
        ))
        # today: mostly YouTube
        s.add(ApplicationEvent(
            id=uuid.uuid4(), organization_id=org_id, employee_id=emp_id, device_id=uuid.uuid4(),
            application="YouTube", started_at=now(), duration_seconds=3600, occurred_at=now(), event_key="t1",
        ))
        await s.commit()
    async with get_sessionmaker()() as s:
        emp = (await s.execute(select(Employee).where(Employee.id == emp_id))).scalar_one()
        result = await ai_service.anomaly(s, org_id, emp, day)
        assert result["facts"]["anomalous"] is True
        assert any(c["name"] == "YouTube" for c in result["facts"]["changes"])


# ---- HTTP smoke ----
async def _admin(client, super_admin):
    root = await login(client, super_admin["slug"], super_admin["email"], super_admin["password"])
    await client.post(
        "/api/v1/organizations", headers=auth_header(root),
        json={"name": "Acme", "slug": "acme", "timezone": "UTC",
              "admin_email": "admin@acme.test", "admin_password": "acmepass123", "admin_full_name": "A"},
    )
    admin = await login(client, "acme", "admin@acme.test", "acmepass123")
    return auth_header(admin)


@pytest.mark.asyncio
async def test_ai_ask_endpoint_respects_scope(client, super_admin):
    h = await _admin(client, super_admin)
    resp = await client.post("/api/v1/ai/ask", headers=h, json={"question": "which applications consumed the most time?"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "nl_query"


@pytest.mark.asyncio
async def test_ai_summary_out_of_scope_returns_403(client, super_admin):
    h = await _admin(client, super_admin)
    # random employee id that doesn't exist -> ScopeDenied -> 403
    resp = await client.post(
        "/api/v1/ai/summary", headers=h,
        json={"scope": "employee", "id": str(uuid.uuid4())},
    )
    assert resp.status_code == 403
