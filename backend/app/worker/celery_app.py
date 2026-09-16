"""Celery application + beat schedule (spec 14, 56).

Runs the auto shift lifecycle periodically. Redis is the broker/result backend. In
production Celery beat runs as a single leader; the tasks iterate active organizations and
apply the scheduler operations with each org's RLS scope set.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "rwm",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "ensure-daily-shifts": {
            "task": "app.worker.tasks.ensure_daily_shifts_all",
            "schedule": 300.0,  # every 5 minutes; idempotent
        },
        "auto-start": {
            "task": "app.worker.tasks.auto_start_all",
            "schedule": 60.0,
        },
        "auto-end": {
            "task": "app.worker.tasks.auto_end_all",
            "schedule": 60.0,
        },
        "mark-missed": {
            "task": "app.worker.tasks.mark_missed_all",
            "schedule": 300.0,
        },
        "purge-expired-screenshots": {
            "task": "app.worker.tasks.purge_screenshots_all",
            "schedule": 3600.0,  # hourly retention sweep
        },
        "detect-monitoring-lost": {
            "task": "app.worker.tasks.detect_monitoring_lost_all",
            "schedule": 120.0,
        },
        "compute-rollups": {
            "task": "app.worker.tasks.compute_rollups_all",
            "schedule": 600.0,  # refresh dashboards' rollups every 10 minutes
        },
        "evaluate-alerts": {
            "task": "app.worker.tasks.evaluate_alerts_all",
            "schedule": 300.0,
        },
        "deliver-webhooks": {
            "task": "app.worker.tasks.deliver_webhooks_all",
            "schedule": 30.0,
        },
    },
)

# Ensure task module is imported so tasks register.
from app.worker import tasks  # noqa: E402,F401
