# 00 — Analysis: Ambiguities, Risks, and Component Responsibilities

This document covers spec section 104 items 1, 2, 13, 14, 15, 16. It is the pre-code
analysis that every later design document builds on. Nothing here is production code;
it is the reasoning that constrains the design.

---

## 1. Ambiguities requiring a decision

These are places where the spec leaves a genuine choice open. Each has a **proposed
default** so implementation is not blocked, but each should be explicitly confirmed.

| # | Ambiguity | Options | Proposed default |
|---|-----------|---------|------------------|
| A1 | Multi-tenant isolation model | (a) shared schema + `organization_id` on every row + row-level security, (b) schema-per-tenant, (c) database-per-tenant | **(a) shared schema + Postgres RLS.** Simplest to operate at 10–10k employees; RLS enforces isolation at the DB layer, not just in app code. Revisit (c) only for a very large single customer. |
| A2 | "Website monitoring" scope | (a) domain only, (b) domain + URL category, (c) full URL | **(a) domain-only by default**, (b) opt-in per policy. Full URL capture is off by default for privacy. Browser data requires a browser extension or native messaging host; agent alone cannot read another browser's URLs reliably. |
| A3 | Screenshot storage crypto | client-side vs server-side encryption at rest | **Server-side envelope encryption** (per-object data key wrapped by a tenant KMS key). Agent uploads over TLS to a pre-signed URL; worker encrypts before final storage, or uses bucket SSE-KMS. |
| A4 | Real-time transport | raw WebSockets vs managed pub/sub (e.g. Redis + WS gateway) | **WebSocket gateway backed by Redis pub/sub.** Horizontal scale without sticky sessions beyond the WS layer. |
| A5 | "Productivity indicator" formula | fixed vs configurable | **Configurable per org** with a documented default formula (see doc 27 note). Never present as an absolute performance score. |
| A6 | Idle default classification | break / idle / working | Spec says default **Idle**. Confirmed. Configurable per policy. |
| A7 | Timezone authority for "today" | employee tz vs org tz | **Attendance day boundaries computed in the employee's effective timezone**, all storage in UTC. |
| A8 | Desktop language | spec recommends C#/.NET | **C#/.NET (WinUI/WPF tray app + Windows service split)** for Windows. Abstract OS-specific collectors behind interfaces for future macOS/Linux. |
| A9 | Background job framework | Celery vs RQ vs Arq | **Celery** (mature, beat scheduler, retries, routing). Redis as broker + result backend. |
| A10 | AI layer hosting | self-hosted model vs external API | **Pluggable provider interface.** AI is optional and must run strictly within RBAC scope (spec 89/90). No provider hard-coded. |
| A11 | "Signed desktop-agent requests" | mTLS vs request signing (HMAC) vs both | **Device-scoped signing key + short-lived access token.** mTLS optional for high-security tenants. |

---

## 2. Technical risks

| # | Risk | Impact | Mitigation |
|---|------|--------|-----------|
| T1 | High-volume ingestion (activity/app/website events at 10k employees) | DB write pressure, cost | Batch + idempotent ingest, async queue, time-partitioned tables, aggregation/rollup tables, object storage for blobs. |
| T2 | Browser URL/domain capture reliability | Feature may silently under-report | Ship optional browser extension / native messaging host; degrade to active-window/domain heuristics; clearly document limits. |
| T3 | Clock tampering on client (edge case 5) | Fraudulent attendance | Server is the sole time authority; agent timestamps are advisory and reconciled against server-received time + heartbeat cadence. |
| T4 | Screenshot storage growth | Cost, retention compliance | Compression, configurable retention with automated deletion + audit, lifecycle policies on object storage. |
| T5 | Offline sync duplication / ordering (edge cases 1, 14) | Double-counted time | Client-generated UUID `event_id`, server-side idempotency keys, monotonic sequence per device. |
| T6 | Schedule/holiday changes mid-shift (edge cases 17, 18) | Inconsistent attendance derivation | Snapshot the effective policy + schedule onto the shift at start; recompute attendance from immutable shift events, not live config. |
| T7 | State-machine races (double start, edge case 8) | Corrupt shift state | Enforce transitions server-side with a DB unique constraint on "one active shift per employee" + optimistic locking. |
| T8 | Agent auto-update supply chain (spec 96) | Malicious update | Signed artifacts, signature verification before install, version pinning, min-supported-version gate. |

---

## 3. Security & privacy risks

| # | Risk | Mitigation |
|---|------|-----------|
| S1 | Tenant data leakage | Postgres RLS keyed on `organization_id`, tenant scoping enforced in a single data-access layer, tests for isolation (spec 80). |
| S2 | Over-collection of sensitive data | Hard rule: never capture passwords, keystroke content, clipboard, private messages, auth tokens. Aggregate-only keyboard/mouse. Enforced in agent collectors + reviewed. |
| S3 | Screenshot exposure | Encrypted in transit + at rest, access-controlled, every view/download audited (spec 86). |
| S4 | Privilege escalation via client | All authorization server-side; client authz is UX only (spec 100). |
| S5 | Token/secret handling | Short-lived access tokens + refresh, secret manager, no secrets in agent binary, encrypted local queue. |
| S6 | AI bypassing permissions | AI queries execute inside the caller's RBAC scope; no privileged data path (spec 90). |
| S7 | Audit tampering | Audit log append-only from app interface; writes via a dedicated path; no update/delete API. |
| S8 | Employee notice/consent | Monitoring toggles visible to admins; policy preview (spec 84); document employee-notice requirement (org responsibility). |

---

## 4. Scalability risks

| # | Risk | Mitigation |
|---|------|-----------|
| C1 | Event table hotspots | Partition `application_events`, `website_events`, `activity_intervals`, `screenshots` by time (monthly) + org; archive old partitions. |
| C2 | Dashboard aggregation cost | Precomputed rollups (daily per employee/team/dept) via workers + materialized views; dashboards read rollups, not raw events. |
| C3 | WebSocket fan-out | Redis pub/sub, stateless WS gateway, presence in Redis with TTL from heartbeats. |
| C4 | Report generation load | Async report jobs, paginated exports, streamed CSV. |
| C5 | Screenshot pipeline | Async upload via pre-signed URLs, worker post-processing, backpressure via queue depth metrics. |

---

## 5. Component responsibility split (spec 104.16)

**Backend API (FastAPI) — authoritative for all policy and truth**
- Auth, RBAC, tenant scoping
- Shift state machine + transition validation
- Attendance derivation, lateness/overtime/break rules
- Server time authority
- Event ingestion (idempotent), classification, policy resolution
- Report/timesheet/leave/correction workflows
- Screenshot metadata + pre-signed URL issuance
- Audit logging

**Background workers (Celery) — async & scheduled**
- Auto-start / auto-end scheduler (Celery beat)
- Rollup/aggregation, materialized-view refresh
- Alert evaluation, notifications, email
- Screenshot post-processing (compress/encrypt/watermark), retention deletion
- Report generation, scheduled reports
- AI summaries/anomaly jobs

**Web app (Next.js) — presentation & control only**
- Dashboards, timelines, viewers, admin settings, policy preview
- Requests actions; renders server-decided truth; never computes lateness/time locally

**Desktop agent (C#/.NET) — collection & local UX only**
- Auth, device identity, schedule sync, tray UI, shift controls (requests)
- Collectors: active/idle, app usage, domain (where permitted), aggregate kbd/mouse, screenshots
- Heartbeat, encrypted offline queue, batched idempotent sync, notifications
- Enforces monitoring locally as directed but is never the source of truth

---

## 6. Guiding invariant

**The backend is the source of truth.** The client requests; the server validates policy
and records the authoritative event. Every design doc that follows must preserve this.
