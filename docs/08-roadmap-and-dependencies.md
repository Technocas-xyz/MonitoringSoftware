# 08 — Development Roadmap & Dependencies

Covers spec section 104.12 and 104.13, aligned to the phased plan in spec 97 and the
Definition of Done in spec 103. Each phase lists what to build, its dependencies, and the
exit criteria that must pass before moving on.

Rule (spec 98): every feature ships the full slice — DB model, API, business logic,
permission checks, UI, desktop integration (if applicable), error handling, logging, audit,
tests. No mock-and-call-it-done.

---

## Dependency graph (phase level)

```text
P1 Foundation
   └─► P2 Attendance & Shifts
         └─► P3 Desktop Agent
               └─► P4 Monitoring
                     └─► P5 Productivity Analytics
                           ├─► P6 Projects & Timesheets
                           └─► P7 Alerts & Reports
                                 └─► P8 AI
                                       └─► P9 Advanced
```
P6 and P7 can run in parallel after P5. P0 (platform scaffolding) precedes P1.

---

## Phase 0 — Platform scaffolding (prereq)

Build: monorepo layout, Docker Compose (postgres, redis, minio, api, worker, beat, web, proxy),
Alembic migration harness, config/secrets loading, structured logging, CI (lint/test/build),
OpenAPI generation + typed frontend client, base RLS session wiring, health endpoints.
**Depends on:** docs 01–03. **Exit:** compose up runs; migrations apply; health green; CI passes.

## Phase 1 — Foundation (spec 97.P1)

Build: auth (login, JWT+refresh, 2FA), organizations + tenant context/RLS, users, employees,
departments, teams, roles + permissions + matrix seed (doc 07), device registration skeleton,
audit writer, basic dashboard shell.
**Depends on:** P0. **Exit:** multi-tenant isolation test passes; RBAC enforced; audit records
written; admin can create org/dept/team/employee/user.

## Phase 2 — Attendance & Shifts (spec 97.P2) — must be fully functional before monitoring

Build: work_schedules (fixed/flexible/rotating/custom) + assignments, shift + monitoring
policies + inheritance resolver + `/policies/preview`, shift state machine (doc 04) with
start/pause/resume/end + guards, breaks, auto-start/auto-end scheduler (Celery beat),
attendance derivation (late/absent/partial/early-leave/overtime), leave + holidays, server
time authority.
**Depends on:** P1. **Exit:** state-machine + attendance test suite (spec 80) green; auto
start/end verified; one-active-shift enforced; policy preview matches applied policy.

## Phase 3 — Windows Desktop Agent (spec 97.P3)

Build: service+tray split (doc 05), device enrollment + approval + signed device tokens,
schedule sync, shift controls (start/pause/resume/end via API), heartbeat, encrypted offline
queue (SQLite), idempotent batch sync, notifications.
**Depends on:** P2, API auth/shift/ingest contracts (doc 03). **Exit:** offline→online sync
with no duplicates; lifecycle replay validated server-side; heartbeat drives presence.

## Phase 4 — Monitoring (spec 97.P4)

Build: collectors (active/idle, applications, websites domain-first, aggregate kbd/mouse),
screenshots (presign→upload→confirm→post-process→retention), ingestion pipeline
(partitioned tables), monitoring-policy enforcement + state-gated capture, privacy guarantees
(never-collect list enforced in collectors).
**Depends on:** P3, object storage. **Exit:** monitoring starts/stops with shift state; idle
detection; app/website tracking; screenshot capture + retention deletion + access logging;
offline monitoring buffered.

## Phase 5 — Productivity Analytics (spec 97.P5)

Build: productivity categories + per-scope classifications, indicator computation (configurable
formula), daily/team/dept rollups + materialized views, employee timeline, manager dashboard,
live board (WS presence), heatmap, trends/comparisons.
**Depends on:** P4. **Exit:** dashboards read rollups (not raw events); timeline/heatmap/trends
render; classification differs correctly per department.

## Phase 6 — Projects & Timesheets (spec 97.P6)

Build: projects/tasks, task timers (agent + manual), timesheets (submit/approve/reject/edit/lock),
corrections workflow, project costing (rate-gated).
**Depends on:** P5. **Exit:** time attributed to tasks; approval + correction flows audited;
costing restricted to `rate.view`.

## Phase 7 — Alerts & Reports (spec 97.P7)

Build: alert rule engine (late/idle/unproductive/missed/monitoring-lost/early-departure) +
evaluation workers, notification channels + templates, report builders + CSV/Excel/PDF export,
scheduled reports, webhooks.
**Depends on:** P5. **Exit:** all example alerts fire; reports export in 3 formats with filters;
scheduled reports delivered; webhooks signed + retried.

## Phase 8 — AI (spec 97.P8)

Build: pluggable provider interface, daily employee/team summaries, anomaly detection,
NL analytics — all executed strictly within caller RBAC scope (spec 90).
**Depends on:** P5–P7 data. **Exit:** AI cannot access out-of-scope data (test); summaries +
anomaly + NL Q&A return scoped results; no auto-disciplinary actions.

## Phase 9 — Advanced (spec 97.P9)

Build: mobile app (attendance/shift/approvals/notifications), optional GPS/geofencing module,
payroll module (configurable rules), external integrations (HR/payroll/PM/calendar/Slack-Teams),
SSO (Google/Entra/SAML/OIDC), multi-region scaling.
**Depends on:** all prior. **Exit:** modules are opt-in, privacy-controlled, and don't regress
core; SSO login works; horizontal scale validated.

---

## External dependencies / infrastructure

| Need | Choice | Notes |
|------|--------|-------|
| Database | PostgreSQL 15+ | RLS, partitioning, uuidv7 |
| Cache/broker/pubsub | Redis 7+ | Celery broker, presence, rate limits, idempotency |
| Object storage | S3-compatible / MinIO | screenshots + exports; provider-abstracted |
| Async | Celery + Beat | scheduling, rollups, alerts, reports, retention, AI |
| Realtime | WebSockets + Redis pub/sub | presence + push |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2 | |
| Frontend | Next.js, React, TypeScript | OpenAPI-typed client |
| Desktop | .NET 8, WPF/WinUI, encrypted SQLite | Windows first |
| Auth | JWT + refresh, TOTP 2FA, OIDC/SAML | SSO pluggable |
| PDF/Excel | server-side render libs | pluggable |
| AI | provider interface | optional, RBAC-scoped |
| Deploy | Docker Compose (dev), Kubernetes (prod) | Beat single-leader |
| Observability | structured logs + metrics + error tracking | health dashboard |

---

## Cross-cutting workstreams (run through all phases)

- **Security & privacy:** TLS, hashing, 2FA, RLS, encrypted screenshots/queue, signed agent
  requests, rate limiting, secret management, never-collect enforcement.
- **Audit:** every admin + key employee action writes an append-only record.
- **Retention:** per-data-class, configurable, automated deletion with audit.
- **Testing:** shift, attendance, monitoring, security suites (spec 80) grow each phase.
- **Docs & ops:** deployment instructions, backup/restore (spec 93), runbooks.

---

## Definition of Done gate (spec 103)

The platform is production-ready only when every DoD item passes: shift start/pause/resume/end,
enforced + flexible + auto start/end, late/break/overtime/attendance, desktop agent + offline
+ sync, application/website/idle/screenshot monitoring, productivity classification, manager
dashboard, timeline, reports, timesheets, alerts, RBAC, multi-tenancy, audit, retention,
security controls, tests on critical logic, documentation, deployment, backup/restore.

---

## Immediate next step (after approval)

Begin **Phase 0 + Phase 1**: scaffold the repo (Docker Compose, migrations, CI, OpenAPI/typed
client, RLS wiring) and implement auth + tenancy + directory + RBAC seed + audit, each as a
full vertical slice with tests. Hold on Phase 2+ until the foundation exit criteria pass.
