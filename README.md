# MonitoringSoftware

Remote Workforce Monitoring, Attendance, Time Tracking & Productivity Platform.

A modular, multi-tenant platform combining time tracking, attendance, computer-activity
monitoring, and productivity analytics. Backend is the source of truth; the desktop agent and
web clients request actions and render server-decided results.

## Repository layout

```
docs/       Architecture & contract set (start here): analysis, architecture, database ERD,
            API spec, shift state machine, desktop-agent design, frontend map, RBAC/policy
            model, and the phased roadmap.
backend/    FastAPI + SQLAlchemy (async) + Alembic + Celery. Auth, multi-tenancy (Postgres RLS),
            RBAC, shifts/attendance, monitoring ingestion, screenshots, productivity analytics,
            projects/timesheets, alerts/reports, AI layer, SSO/geo/payroll modules.
agent/      C#/.NET 8 Windows desktop agent (service + tray): signed device auth, encrypted
            offline queue, idempotent sync, collectors (app/website/idle/screenshot).
frontend/   Next.js 14 + TypeScript web dashboard (sleek dark/animated): login, dashboard,
            live board, employees + timeline, attendance, shifts, alerts, settings.
docker-compose.yml   Dev stack: Postgres, Redis, MinIO, API.
```

## Implementation status

Phases 0–9 of `docs/08-roadmap-and-dependencies.md` are implemented at the code level.

> **Not yet executed.** This code was authored in an environment without a Python or .NET
> runtime, so it has not been compiled, migrated, or tested by execution. Treat the test
> suites as the first validation step (see below). Expect to fix environment-specific issues
> on the first real run.

## Quick start (Docker)

```bash
docker compose up --build
# API docs: http://localhost:8000/docs

# bootstrap the first platform admin
docker compose exec api python -m app.core.bootstrap root@platform.local "a-strong-password"
```

## Backend tests (SQLite, no Postgres/Docker needed)

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -e ".[dev]"
pytest
```

PostgreSQL Row-Level Security isolation is tested separately:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://rwm:rwm@localhost:5432/rwm_test pytest tests/test_rls_postgres.py
```

## Agent build (needs .NET 8 SDK, Windows)

```bash
cd agent
dotnet restore && dotnet test
```

See `backend/README.md` and `agent/README.md` for details, and `docs/` for the full design.

## Security notes

- The application's database role must NOT be a Postgres superuser or table owner that bypasses
  RLS, or tenant isolation will not hold (RLS uses `FORCE ROW LEVEL SECURITY`).
- Never commit `.env` or real secrets; `.gitignore` excludes them.
