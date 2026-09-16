# 03 — API Specification (REST v1) & Event Ingestion Contract

Covers spec section 104.6, plus 50 (API groups), 51 (shift API), 52 (event API), 78 (webhooks).

- Base path: `/api/v1`
- Format: JSON. Errors follow RFC 7807 (`application/problem+json`).
- Auth: `Authorization: Bearer <access_token>` (users) or device-scoped token (agent).
- All list endpoints: cursor pagination (`?cursor=&limit=`), filtering, and `X-Total-Count` where cheap.
- Every mutating call is tenant-scoped (RLS) and writes an audit record.
- Idempotency: agent write endpoints require an `Idempotency-Key` header and/or per-event `event_id`.

---

## 1. Conventions

**Standard error body**
```json
{ "type": "about:blank", "title": "Validation failed", "status": 422,
  "detail": "scheduled_start is required", "code": "shift.invalid_window",
  "trace_id": "..." }
```

**Auth model**
- User access token: short-lived JWT (≈15 min) + refresh token (rotating).
- Device token: issued at device approval, scoped to `{organization_id, employee_id, device_id}`,
  requests signed with the device key (HMAC over method+path+body+timestamp) to satisfy spec 45/60.
- `2FA` challenge flow on login when `twofa_enabled`.

**Rate limiting**: per-token + per-IP, counters in Redis (spec 45).

---

## 2. Endpoint groups (spec 50)

```text
/auth            /users          /employees      /departments   /teams
/devices         /schedules      /shift-policies /monitoring-policies
/shifts          /shift-events   /attendance     /breaks
/ingest          /applications   /websites       /screenshots
/projects        /tasks          /timesheets     /corrections
/alerts          /alert-rules    /notifications  /reports
/analytics       /audit-logs     /settings       /leave  /holidays
/webhooks        /ai             /realtime (WS)
```

---

## 3. Auth

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/auth/login` | email+password → tokens (or 2FA challenge) |
| POST | `/auth/2fa/verify` | complete 2FA |
| POST | `/auth/refresh` | rotate tokens |
| POST | `/auth/logout` | revoke refresh token |
| GET  | `/auth/sso/{provider}/authorize` | OIDC/SAML start |
| GET  | `/auth/sso/{provider}/callback` | SSO callback |
| POST | `/auth/agent/enroll` | device enrollment (returns pending device) |
| POST | `/auth/agent/token` | device token issuance after approval |

---

## 4. Directory (users, employees, org)

Standard CRUD, all tenant-scoped and permission-gated (see doc 06):
```text
GET/POST            /employees
GET/PATCH/DELETE    /employees/{id}
GET                 /employees/{id}/timeline?date=      (spec 28)
GET                 /employees/{id}/dashboard?date=     (spec 30)
GET/POST            /departments   ...   /departments/{id}
GET                 /departments/{id}/analytics         (spec 31)
GET/POST            /teams         ...   /teams/{id}
GET/POST            /users         ...   /users/{id}
POST                /users/{id}/roles                   (assign scoped role)
```

---

## 5. Devices (spec 42)

```text
GET                 /devices
POST                /devices/{id}/approve
POST                /devices/{id}/revoke
POST                /devices/{id}/replace
GET                 /devices/{id}
```

---

## 6. Scheduling & policy

```text
GET/POST            /schedules            (work_schedules)
POST                /schedules/{id}/assign  {target_type,target_id,effective_from,...}
GET/POST            /shift-policies
GET/POST            /monitoring-policies
POST                /shift-policies/{id}/assign        (with allow_override)
POST                /policies/preview                  (spec 84: resolved policy preview)
GET/POST            /leave                             (leave_requests)
POST                /leave/{id}/approve | /reject
GET/POST            /holidays
```

Policy preview returns the **resolved effective policy** for a target after inheritance
(org → dept → team → employee), used by the admin policy-preview screen.

---

## 7. Shifts (spec 51) — server is authoritative

```text
GET                 /shifts?employee_id=&date=&state=
GET                 /shifts/{id}
POST                /shifts/{id}/start
POST                /shifts/{id}/pause      (break start)
POST                /shifts/{id}/resume
POST                /shifts/{id}/end
POST                /shifts/{id}/force-stop  (manager/admin; audited)
GET                 /shifts/{id}/events      (shift_events)
```

**Start request** (agent or web):
```json
POST /api/v1/shifts/{shift_id}/start
{ "device_id": "DEVICE-123", "client_time": "2026-09-14T09:07:02Z",
  "event_id": "b1e2...uuid" }
```
Server validation (spec 10): employee active, authorized, within allowed window
(server time), no active shift, schedule exists, tz applied, policy permits, device approved.
On success → transitions state, writes `SHIFT_START`, returns the shift with computed fields.

**Response (shape for all shift actions)**:
```json
{ "id":"SHIFT-456","state":"WORKING","scheduled_start":"...","actual_start":"...",
  "worked_seconds":0,"break_seconds":0,"idle_seconds":0,
  "late_seconds":420,"overtime_seconds":0,
  "monitoring": {"applications":true,"websites":true,"screenshots":"interval","idle":true} }
```

Invalid transitions return `409 shift.invalid_transition` with the current state.
Starting before window → `422 shift.window_not_open`. Duplicate active shift →
`409 shift.already_active`.

---

## 8. Event ingestion contract (spec 52) — idempotent, offline-tolerant

Single batch endpoint for all agent monitoring events:

```json
POST /api/v1/ingest/events
Headers: Authorization: Bearer <device_token>, Idempotency-Key: <batch-uuid>
{
  "device_id": "DEVICE-123",
  "shift_id": "SHIFT-456",
  "sequence": 10421,                        // monotonic per device
  "events": [
    { "event_id":"EVT-1", "type":"APPLICATION_ACTIVITY",
      "timestamp":"2026-09-14T09:30:00Z", "application":"Code",
      "process":"Code.exe", "window_title":"main.py", "duration":600 },
    { "event_id":"EVT-2", "type":"WEBSITE_ACTIVITY",
      "timestamp":"2026-09-14T09:41:00Z", "domain":"github.com", "duration":120 },
    { "event_id":"EVT-3", "type":"ACTIVITY_INTERVAL",
      "interval_start":"09:30", "interval_end":"09:40",
      "keyboard_pct":42, "mouse_pct":61, "combined_pct":53, "is_idle":false },
    { "event_id":"EVT-4", "type":"IDLE",
      "interval_start":"10:18", "interval_end":"10:31" },
    { "event_id":"EVT-5", "type":"SCREENSHOT_META",
      "timestamp":"09:35", "captured_at":"09:35", "bytes":48211 }
  ]
}
```

**Server rules**
- Each `event_id` is a client-generated UUID. Server dedupes on
  `(organization_id, event_key)` where `event_key = event_id`. Re-sent batches are safe.
- `type` accepted: `APPLICATION_ACTIVITY`, `WEBSITE_ACTIVITY`, `ACTIVITY_INTERVAL`,
  `IDLE`, `SCREENSHOT_META`, plus shift lifecycle events when replayed from offline queue
  (`SHIFT_START`, `BREAK_START`, `BREAK_END`, `RESUME`, `SHIFT_END`).
- Server assigns authoritative `occurred_at`/reconciliation; client timestamps are advisory.
- Server enqueues persistence + classification to Celery; endpoint returns fast.
- `window_title`/`url` are dropped server-side if the resolved monitoring policy forbids them.

**Response**
```json
{ "accepted": 5, "duplicates": 0, "rejected": 0,
  "next_sequence_ack": 10421 }
```

**Screenshot upload flow**
```text
POST /api/v1/screenshots/presign  {captured_at, bytes, shift_id}  -> {upload_url, storage_key, screenshot_id}
PUT  <upload_url>  (agent uploads encrypted blob directly to object storage)
POST /api/v1/screenshots/{id}/confirm  -> worker post-processes, applies retention_until
```
Viewing:
```text
GET  /api/v1/screenshots?employee_id=&date=&shift_id=
GET  /api/v1/screenshots/{id}/url   (short-lived signed URL; logs access — spec 86)
```

---

## 9. Heartbeat (spec 18)

```json
POST /api/v1/devices/{id}/heartbeat
{ "employee_id":"...", "shift_id":"...", "agent_version":"1.2.0", "os":"windows",
  "online":true, "tracking_state":"WORKING", "timestamp":"...", "net":{"type":"wifi"} }
```
Updates `devices.last_seen_at` + Redis presence (TTL). Never used alone for productivity.

---

## 10. Attendance, timesheets, corrections

```text
GET     /attendance?employee_id=&from=&to=&status=
GET     /timesheets?employee_id=&period=
POST    /timesheets/{id}/submit
POST    /timesheets/{id}/approve | /reject
POST    /timesheets/{id}/lock
POST    /corrections                    (employee submits)
POST    /corrections/{id}/approve | /reject
```

---

## 11. Projects, tasks, task time

```text
GET/POST  /projects   ...  /projects/{id}
GET/POST  /tasks?project_id=  ... /tasks/{id}
POST      /tasks/{id}/start   (employee selects task; starts task timer)
POST      /tasks/{id}/stop
GET       /projects/{id}/costing        (restricted: rate access)
```

---

## 12. Productivity & classification

```text
GET/POST  /productivity/categories
GET/POST  /applications/classifications   (scoped org|dept|team)
GET/POST  /websites/classifications
```

---

## 13. Alerts, notifications, reports, analytics

```text
GET/POST  /alert-rules   ...  /alert-rules/{id}
GET       /alerts?status=&severity=&from=&to=
POST      /alerts/{id}/acknowledge | /resolve
GET       /notifications      POST /notifications/{id}/read
POST      /reports/generate   {type, format, filters}   -> async job id
GET       /reports/jobs/{id}                             -> status + download url
GET/POST  /report-schedules
GET       /analytics/overview                            (spec 102 dashboard)
GET       /analytics/heatmap?employee_id=&date=          (spec 87)
GET       /analytics/trends?scope=&metric=&range=        (spec 88)
GET       /analytics/applications  /analytics/websites   (spec 32/33)
```

---

## 14. AI (RBAC-scoped — spec 89/90)

```text
POST  /ai/summary        {scope: employee|team|dept, id, date}
POST  /ai/anomaly        {employee_id, date}
POST  /ai/ask            {question}    -> executes within caller RBAC scope only
GET   /ai/jobs/{id}
```
AI queries never bypass permissions; the caller's scope is snapshotted onto `ai_jobs.scope`
and all data access is filtered by it.

---

## 15. Audit, settings, webhooks

```text
GET   /audit-logs?actor=&action=&from=&to=   (read-only; no write/delete API)
GET/PATCH  /settings                          (org settings, retention, privacy toggles)
GET/POST   /webhooks   ...   /webhooks/{id}
POST       /webhooks/{id}/test
```

**Webhook events emitted** (spec 78):
`shift.started`, `shift.paused`, `shift.resumed`, `shift.ended`,
`attendance.late`, `attendance.absent`, `timesheet.approved`, `alert.created`.
Signed with per-webhook secret (HMAC), delivered with retries via worker.

---

## 16. Realtime (WebSocket — spec 48)

```text
WSS /api/v1/realtime?token=<access>
```
- Server → client messages: `presence.update`, `alert.created`, `shift.state_changed`,
  `notification.new`.
- Subscriptions scoped by RBAC (a manager only receives their team's presence).
- Presence sourced from heartbeats + shift state, fanned out via Redis pub/sub.

---

## 17. Idempotency & consistency summary

| Concern | Mechanism |
|---------|-----------|
| Duplicate shift actions | `shift_events.event_key` unique + state-machine guard |
| Duplicate monitoring events | `event_key` unique per partitioned table |
| Duplicate batches | `Idempotency-Key` cached in Redis + per-event dedupe |
| Ordering | per-device monotonic `sequence`; server reconciles, tolerates gaps |
| Time authority | server assigns `occurred_at`; client time advisory only |
