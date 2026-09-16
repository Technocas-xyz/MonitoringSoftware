"""FastAPI application factory and router wiring."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.auth_router import router as agent_auth_router
from app.agent.router import router as agent_router
from app.ai.router import router as ai_router
from app.alerts.router import router as alerts_router
from app.audit.router import router as audit_router
from app.auth.router import router as auth_router
from app.geo.router import router as geo_router
from app.payroll.router import router as payroll_router
from app.reports.router import router as reports_router
from app.settings.router import router as settings_router
from app.sso.router import router as sso_router
from app.webhooks.router import router as webhooks_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.devices.router import router as devices_router
from app.directory.provisioning_router import router as provisioning_router
from app.directory.router import router as directory_router
from app.analytics.router import router as analytics_router
from app.ingestion.router import router as ingestion_router
from app.policy.router import router as policy_router
from app.productivity.router import router as productivity_router
from app.projects.router import router as projects_router
from app.screenshots.router import router as screenshots_router
from app.timesheets.router import router as timesheets_router
from app.scheduling.leave_router import router as leave_router
from app.scheduling.router import router as scheduling_router
from app.shifts.attendance_router import router as attendance_router
from app.shifts.router import router as shifts_router

configure_logging(settings.debug)
log = get_logger()

API_V1 = "/api/v1"


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        openapi_url=f"{API_V1}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router, prefix=API_V1)
    app.include_router(provisioning_router, prefix=API_V1)
    app.include_router(directory_router, prefix=API_V1)
    app.include_router(devices_router, prefix=API_V1)
    app.include_router(audit_router, prefix=API_V1)
    app.include_router(policy_router, prefix=API_V1)
    app.include_router(scheduling_router, prefix=API_V1)
    app.include_router(leave_router, prefix=API_V1)
    app.include_router(shifts_router, prefix=API_V1)
    app.include_router(attendance_router, prefix=API_V1)
    app.include_router(agent_auth_router, prefix=API_V1)
    app.include_router(agent_router, prefix=API_V1)
    app.include_router(ingestion_router, prefix=API_V1)
    app.include_router(screenshots_router, prefix=API_V1)
    app.include_router(productivity_router, prefix=API_V1)
    app.include_router(analytics_router, prefix=API_V1)
    app.include_router(projects_router, prefix=API_V1)
    app.include_router(timesheets_router, prefix=API_V1)
    app.include_router(alerts_router, prefix=API_V1)
    app.include_router(reports_router, prefix=API_V1)
    app.include_router(webhooks_router, prefix=API_V1)
    app.include_router(ai_router, prefix=API_V1)
    app.include_router(sso_router, prefix=API_V1)
    app.include_router(geo_router, prefix=API_V1)
    app.include_router(payroll_router, prefix=API_V1)
    app.include_router(settings_router, prefix=API_V1)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "app": settings.app_name, "env": settings.environment}

    return app


app = create_app()
