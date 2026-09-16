# 01 — Proposed System Architecture

Covers spec section 104.3, plus 56 (stack), 57 (architecture), 58 (scalability), 91 (deployment).

---

## 1. High-level architecture

```text
                         WEB DASHBOARD (Next.js / React / TS)
                                      |
                                   HTTPS / WSS
                                      |
                          ┌───────────┴───────────┐
                          |     Reverse Proxy      |   (TLS termination, routing,
                          |   (Nginx / Traefik)    |    rate limiting)
                          └───────────┬───────────┘
                    ┌─────────────────┼──────────────────┐
                    |                 |                  |
              FastAPI API        WS Gateway         Static / Next.js
              (stateless,        (presence,          server
               horizontally      realtime push)
               scalable)
                    |                 |
          ┌─────────┼─────────────────┼──────────────────────────┐
          |         |                 |                          |
     PostgreSQL   Redis          Object Storage             Celery Workers
     (+ RLS,      (broker,       (S3 / MinIO,               + Celery Beat
      partitions) cache,          screenshots,              (scheduler)
                  pub/sub,        encrypted)
                  presence)
          ^                                                       |
          |                                                       |
          └──────────────── shared data plane ────────────────────┘

                                      ^
                                      | HTTPS / WSS (signed, device-scoped tokens)
                                      |
                          WINDOWS DESKTOP AGENT (C#/.NET)
                          ┌───────────┼──────────────┐
                     Shift Engine  Collectors    Screenshot
                     (local UX)    (app/idle/     capture
                                    domain/kbd)
                          └───────────┼──────────────┘
                                      |
                              Local Encrypted Queue (offline buffer)
```

The web app and desktop agent both talk only to the API and WS gateway over TLS.
No client component reads or writes the database directly.

---

## 2. Services and responsibilities

| Service | Tech | Scaling | Responsibility |
|---------|------|---------|----------------|
| API | FastAPI (Python 3.12), SQLAlchemy 2.x, Pydantic v2 | Stateless, N replicas behind proxy | Auth, RBAC, tenant scoping, shift state machine, attendance rules, event ingestion, screenshot presign, reports orchestration, audit |
| WS Gateway | FastAPI/Starlette WebSockets (or dedicated ASGI service) | Stateless, N replicas; state in Redis | Realtime presence + push to dashboards; subscribes to Redis pub/sub |
| Worker | Celery | N workers by queue | Async ingestion post-processing, rollups, alerts, notifications, screenshots, reports, retention, AI |
| Scheduler | Celery Beat (single leader) | 1 (with lock) | Auto-start/auto-end, periodic rollups, scheduled reports, retention sweeps |
| PostgreSQL | 15+ | Primary + read replicas | System of record; RLS for tenant isolation; partitioned high-volume tables |
| Redis | 7+ | Cluster/Sentinel | Broker, cache, pub/sub, presence, rate-limit counters, idempotency keys |
| Object Storage | S3-compatible / MinIO | Managed | Encrypted screenshots + report exports |
| Reverse proxy | Nginx / Traefik | N | TLS, routing, rate limiting, WS upgrade |

---

## 3. Technology stack (from spec 56, confirmed)

- **Frontend:** Next.js + React + TypeScript. Data fetching via typed client generated from the OpenAPI schema. Charts for heatmaps/trends.
- **Backend:** Python + FastAPI + SQLAlchemy + Alembic (migrations) + Pydantic v2.
- **Datastore:** PostgreSQL (primary), Redis (broker/cache/pubsub).
- **Async:** Celery + Celery Beat.
- **Realtime:** WebSockets + Redis pub/sub.
- **Desktop:** C#/.NET on Windows — a Windows **service** (collection, always-on) plus a **tray app** (UX). Split so collection survives UI restarts.
- **Object storage:** S3-compatible, MinIO for self-hosted. Provider abstracted behind a storage interface.

---

## 4. Backend internal structure (modular, not monolithic — spec 105)

Domain modules with clear interfaces; each owns its models, services, schemas, routes:

```text
app/
  core/           config, security, db session, RLS context, time authority, deps
  auth/           login, tokens, 2FA, SSO adapters
  tenancy/        organization, tenant context middleware
  directory/      users, employees, departments, teams, roles, permissions (RBAC)
  devices/        device registration, approval, revocation, versions
  scheduling/     work_schedules, schedule_assignments, holidays, leave
  policy/         shift_policies, monitoring_policies, inheritance resolver
  shifts/         shift state machine, shift_events, breaks
  attendance/     derivation engine (reads shift_events), statuses
  activity/       ingestion, application_events, website_events, activity_intervals, idle
  screenshots/    presign, metadata, retention, viewer access logging
  productivity/   categories, classifications, indicator computation
  projects/       projects, tasks, task_time_entries
  timesheets/     timesheets, approvals, corrections
  alerts/         rule engine, evaluation
  notifications/  channels, templates
  reports/        report builders, exports (csv/xlsx/pdf), scheduling
  analytics/      rollups, trends, heatmaps, comparisons
  ai/             provider interface, summaries, anomaly, NL query (RBAC-scoped)
  audit/          append-only audit writer + query
  realtime/       WS gateway, presence, pubsub publishers
  ingestion_worker/ celery tasks per domain
```

Cross-cutting rules:
- Every DB query passes through a tenant-scoped session (RLS `SET app.current_org`).
- Every mutating endpoint writes an audit record via the `audit` module.
- Business logic lives in services, never in route handlers or the client.

---

## 5. Data flow examples

**Start shift**
1. Agent → `POST /shifts/{id}/start` with device token.
2. API validates: employee active, authorized, within window, no active shift, device approved, policy permits (see doc 04 state machine).
3. API snapshots effective policy+schedule onto the shift, transitions `AVAILABLE → WORKING`, writes `SHIFT_START` event + audit, enables monitoring flags.
4. API publishes presence update to Redis → WS gateway → manager dashboards.

**Activity ingestion (batched, offline-tolerant)**
1. Agent buffers events locally (encrypted) with UUID `event_id` + device sequence.
2. On connectivity: `POST /ingest/events` batch.
3. API dedupes by `event_id` (idempotency), enqueues raw persist + classification to Celery.
4. Worker persists to partitioned tables, updates rollups, evaluates alerts.

**Screenshot**
1. Agent requests presigned upload URL (metadata registered).
2. Agent uploads encrypted blob directly to object storage over TLS.
3. Worker post-processes (compress/watermark), confirms, applies retention TTL.

---

## 6. Deployment topology (spec 91)

- **Dev:** Docker Compose — api, ws, worker, beat, postgres, redis, minio, proxy, web.
- **Prod:** Kubernetes-compatible. Each service a Deployment; Beat as a single-replica Deployment with leader lock; Postgres managed/HA; Redis HA; object storage managed; HPA on api/ws/worker by CPU + queue depth.
- Config via environment + secret manager. No secrets in images.

---

## 7. Observability & health (spec 92, 94)

- Structured JSON logging with request/trace IDs and `organization_id`.
- Metrics: API latency, error rate, queue depth per Celery queue, worker health, WS connections, screenshot pipeline failures, agent connected/offline counts.
- Health endpoints for API/DB/Redis/workers feeding the admin health dashboard.
- Error tracking integration (pluggable).

---

## 8. Non-negotiable architectural invariants

1. Backend is the source of truth (spec 100).
2. Tenant isolation enforced at the DB layer (RLS), not only in app code.
3. High-volume monitoring data is append-only, partitioned, and rolled up for reads.
4. Attendance is **derived** from immutable shift/events, never the primary store (spec 54).
5. Screenshots never stored as blobs in Postgres (spec 55).
6. Sensitive input (passwords/keystrokes/clipboard/messages/tokens) is never collected.
