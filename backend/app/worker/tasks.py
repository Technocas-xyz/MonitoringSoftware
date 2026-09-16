"""Celery tasks driving the auto shift lifecycle across all organizations.

Each task iterates active organizations, opens a tenant-scoped session per org (RLS set), and
runs the corresponding scheduler operation. Async scheduler functions are executed via
asyncio.run inside the synchronous Celery task.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.core.tenant import open_tenant_session
from app.core.time_authority import now
from app.models.organization import Organization
from app.shifts import scheduler
from app.worker.celery_app import celery_app


async def _list_org_ids() -> list[uuid.UUID]:
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(Organization.id).where(Organization.status == "active")
            )
        ).scalars().all()
    return list(rows)


async def _run_per_org(op_name: str) -> int:
    total = 0
    for org_id in await _list_org_ids():
        async with open_tenant_session(str(org_id)) as session:
            op = getattr(scheduler, op_name)
            if op_name == "ensure_daily_shifts":
                count = await op(session, org_id, now().date())
            else:
                count = await op(session, org_id)
            await session.commit()
            total += count
    return total


@celery_app.task(name="app.worker.tasks.ensure_daily_shifts_all")
def ensure_daily_shifts_all() -> int:
    return asyncio.run(_run_per_org("ensure_daily_shifts"))


@celery_app.task(name="app.worker.tasks.auto_start_all")
def auto_start_all() -> int:
    return asyncio.run(_run_per_org("run_auto_start"))


@celery_app.task(name="app.worker.tasks.auto_end_all")
def auto_end_all() -> int:
    return asyncio.run(_run_per_org("run_auto_end"))


@celery_app.task(name="app.worker.tasks.mark_missed_all")
def mark_missed_all() -> int:
    return asyncio.run(_run_per_org("mark_missed"))


async def _purge_screenshots() -> int:
    from app.screenshots.worker_ops import purge_expired_screenshots

    total = 0
    for org_id in await _list_org_ids():
        async with open_tenant_session(str(org_id)) as session:
            total += await purge_expired_screenshots(session, org_id)
            await session.commit()
    return total


@celery_app.task(name="app.worker.tasks.purge_screenshots_all")
def purge_screenshots_all() -> int:
    return asyncio.run(_purge_screenshots())


@celery_app.task(name="app.worker.tasks.detect_monitoring_lost_all")
def detect_monitoring_lost_all() -> int:
    return asyncio.run(_run_per_org("detect_monitoring_lost"))


async def _compute_rollups() -> int:
    from app.productivity.rollups import compute_org_rollups

    total = 0
    for org_id in await _list_org_ids():
        async with open_tenant_session(str(org_id)) as session:
            total += await compute_org_rollups(session, org_id, now().date())
            await session.commit()
    return total


@celery_app.task(name="app.worker.tasks.compute_rollups_all")
def compute_rollups_all() -> int:
    return asyncio.run(_compute_rollups())


async def _evaluate_alerts() -> int:
    from app.alerts.engine import evaluate_org

    total = 0
    for org_id in await _list_org_ids():
        async with open_tenant_session(str(org_id)) as session:
            total += await evaluate_org(session, org_id, now().date())
            await session.commit()
    return total


@celery_app.task(name="app.worker.tasks.evaluate_alerts_all")
def evaluate_alerts_all() -> int:
    return asyncio.run(_evaluate_alerts())


async def _deliver_webhooks() -> int:
    from app.webhooks.service import deliver_pending

    total = 0
    for org_id in await _list_org_ids():
        async with open_tenant_session(str(org_id)) as session:
            total += await deliver_pending(session, org_id)
            await session.commit()
    return total


@celery_app.task(name="app.worker.tasks.deliver_webhooks_all")
def deliver_webhooks_all() -> int:
    return asyncio.run(_deliver_webhooks())
