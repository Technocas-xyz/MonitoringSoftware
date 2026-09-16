# Backend — Remote Workforce Monitoring Platform

FastAPI + PostgreSQL + SQLAlchemy (async) + Alembic. This is **Phase 0 + Phase 1** of the
roadmap in `../docs/08-roadmap-and-dependencies.md`: platform scaffolding plus the foundation
(auth, multi-tenancy with RLS, directory, RBAC, devices skeleton, audit).

## Requirements

- Python 3.11+
- PostgreSQL 15+ (production and for RLS tests)
- Redis (used from Phase 2 onward; not required to run Phase 1)

## Setup

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -e ".[dev]"
cp .env.example .env              # edit SECRET_KEY, DATABASE_URL
```

## Run with Docker Compose (recommended)

From the repository root:

```bash
docker compose up --build
```

This starts PostgreSQL, Redis, MinIO, and the API. The API container runs
`alembic upgrade head` before starting uvicorn.

## Run migrations manually

```bash
cd backend
alembic upgrade head
```

## Bootstrap the first platform super admin

Provisioning organizations requires `platform.admin`, so create the first super admin via CLI:

```bash
python -m app.core.bootstrap root@platform.local "a-strong-password"
```

Then log in at `POST /api/v1/auth/login` with:
```json
{ "organization_slug": "platform", "email": "root@platform.local", "password": "a-strong-password" }
```

Use the returned access token to `POST /api/v1/organizations` and create tenant orgs.

## API docs

Once running: `http://localhost:8000/docs` (OpenAPI at `/api/v1/openapi.json`).

## Tests

Application-level tests (auth, RBAC, directory, audit, devices) run on in-memory SQLite:

```bash
cd backend
pytest
```

PostgreSQL Row-Level Security isolation is a DB-layer feature and is tested separately.
Point the tests at a Postgres database (with migrations applied) to include it:

```bash
# create an empty test DB, apply migrations, then:
TEST_DATABASE_URL=postgresql+asyncpg://rwm:rwm@localhost:5432/rwm_test pytest tests/test_rls_postgres.py
```

## Running the worker + scheduler (Phase 2)

Auto start/end and missed-shift detection run via Celery beat:

```bash
# worker
celery -A app.worker.celery_app.celery_app worker --loglevel=info
# beat scheduler (single leader)
celery -A app.worker.celery_app.celery_app beat --loglevel=info
```

## What's implemented in Phase 9 (Advanced, opt-in modules)

- **SSO:** pluggable provider interface (OIDC/SAML/Google/Entra register here; no hard-coded
  IdP), authorize + callback that links to or provisions a user and issues platform tokens.
  Enabled per org via `settings.sso`.
- **Geolocation/geofencing (opt-in):** office locations + haversine geofence evaluation on
  device location pings. Only active when `settings.geo.enabled`; location data is never stored
  otherwise (privacy-controlled).
- **Payroll (opt-in, restricted):** configurable rules (`settings.payroll`) generating
  regular / overtime / paid-leave / unpaid lines priced by employee rate; gated behind
  `payroll.run`.
- **Settings API:** deep-merge PATCH for retention, privacy toggles, SSO, geo, and payroll.

## What's implemented in Phase 8 (AI)

- **Provider interface:** pluggable `AIProvider`; the default `TemplateProvider` composes
  summaries/answers deterministically with no external calls, so the platform works out of the
  box. An external LLM can be plugged in — it only ever receives pre-authorized facts, never
  database access.
- **RBAC scope guard:** every AI request verifies the target is within the caller's scope
  *before* any data is gathered (org-wide, own team, or self); out-of-scope returns 403. The
  caller's scope is snapshotted onto each `ai_jobs` row (spec 90).
- **Summaries / anomaly / NL:** daily employee & team summaries, anomaly detection (today's
  app-mix vs a trailing baseline), and a bounded natural-language query answered only over
  authorized data. AI never makes disciplinary decisions.

## What's implemented in Phase 7 (Alerts & Reports)

- **Alert engine:** evaluates enabled rules (late arrival, excessive idle/unproductive, missed
  shift, early departure) against attendance + rollups; alerts are deduplicated per
  rule/employee/day and dispatch notifications.
- **Notifications:** `{{placeholder}}` templates rendered per channel; in-app persisted,
  email/push pluggable.
- **Reports:** attendance / productivity / application / website / shift builders with
  CSV / Excel / PDF export (Excel & PDF degrade gracefully to CSV if optional libs absent);
  synchronous download + report schedules.
- **Webhooks:** registration with a one-time secret, HMAC-signed delivery worker with retries,
  and emission of `shift.*`, `attendance.*`, `timesheet.approved`, `alert.created` events.

## What's implemented in Phase 6 (Projects & Timesheets)

- **Projects/tasks:** CRUD + task time tracking with one-open-entry-per-employee (switching
  tasks closes the prior entry) and shift binding.
- **Timesheets:** generated from derived attendance; submit → approve/reject → lock lifecycle;
  locked timesheets are immutable; every manual edit requires a reason and is audited.
- **Corrections:** employees submit correction requests (old/new/reason); reviewers approve or
  reject; all transitions audited.
- **Costing (rate-gated):** project cost = Σ(task-time hours × employee hourly rate), gated by
  `rate.view`.

## What's implemented in Phase 5 (Productivity Analytics)

- **Classification:** productivity categories (configurable weights) + per-scope app/website
  classifications (team > department > organization); the same app can be productive for one
  department and unproductive for another.
- **Indicator:** configurable weighted-ratio "Productivity Indicator" (never an absolute score).
- **Rollups:** a worker aggregates classified events + attendance into daily employee/team/
  department rollups (dashboards read these, not raw events).
- **Analytics APIs:** org overview, employee detail + timeline, activity heatmap, department
  analytics, and current-vs-previous trends — all RBAC scope-narrowed.

## What's implemented in Phase 4 (Monitoring)

- **Ingestion:** `POST /ingest/events` (device-authenticated, idempotent by `event_id`),
  persisting application/website/activity/idle events bound to the employee's active shift.
  Privacy field-dropping is enforced server-side (window titles / full URLs are discarded
  unless the resolved monitoring policy permits them).
- **Screenshots:** pluggable object storage (S3/MinIO + local dev provider), presign → upload
  → confirm flow, short-lived signed view URLs, and **every view/download is access-logged**.
  A retention worker deletes expired screenshots (retention days from org settings) and audits
  each deletion.
- **Idle:** idle intervals fold into attendance `idle_seconds` and reduce worked time unless
  the policy classifies idle as working.
- **Monitoring-lost:** a scheduler check flags active, monitoring-required shifts whose device
  has stopped sending heartbeats (consumed by the Phase 7 alert engine).

## What's implemented in Phase 2

- **Schedules:** fixed / flexible / rotating / custom; assignment by employee/team/department;
  occurrence computation in the employee's effective timezone (UTC storage, DST-aware).
- **Policies:** shift + monitoring policy CRUD; inheritance resolver (org -> dept -> team ->
  employee with `allow_override`); `/policies/preview` returns the resolved effective policy.
- **Shift state machine:** server-authoritative start/pause/resume/end/force-stop with guards
  (clock-in window, break rules, early clock-out, overtime), idempotent events, optimistic
  locking, and a frozen policy snapshot per shift.
- **Breaks & attendance:** break open/close/exceeded; attendance derived from shift + events
  (late/worked/break/early-leave/overtime + status).
- **Leave & holidays:** requests + approval, holiday calendars; both suppress attendance
  violations (missed -> cancelled/rest day).
- **Auto scheduler:** Celery beat drives ensure-daily-shifts, auto-start, auto-end, mark-missed.

## What's implemented in Phase 1

- **Tenancy:** organizations + Postgres RLS (`app.current_org` GUC) on all tenant tables.
- **Auth:** email/password login (scoped by org slug), JWT access + rotating refresh,
  2FA challenge/verify (TOTP), `/me`, logout.
- **RBAC:** permission catalog + system roles (`docs/07`), permission-gated endpoints,
  scope narrowing (managers/supervisors see only their teams; employees see self),
  rate-field gating.
- **Directory:** users, departments, teams, employees (CRUD subset with audit).
- **Devices:** enroll → approve → revoke lifecycle (skeleton for Phase 3 agent).
- **Audit:** append-only writer + read-only API.

## Layout

```
app/
  core/     config, db, tenant (RLS), security, deps, rbac, seed, bootstrap, time, logging
  models/   organization, identity, directory, devices, audit, types (portable), mixins
  auth/     principal, service, schemas, router
  directory/ schemas, provisioning_router, router
  devices/  schemas, router
  audit/    service, router
alembic/    env + versions/0001_initial.py (schema + RLS)
tests/      auth/rbac, directory/audit, rls (postgres-only)
```
