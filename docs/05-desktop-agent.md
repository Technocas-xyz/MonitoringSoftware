# 05 — Desktop Agent Architecture

Covers spec section 104.8, plus 16–19 (agent/UI/heartbeat/offline), 20–24 (collectors),
59 (performance), 60 (security), 95/96 (versioning/auto-update).

Target: **Windows**, C#/.NET. Designed so OS-specific collectors sit behind interfaces to
allow future macOS/Linux. The client is a collector and local UX; **never the source of truth**.

---

## 1. Process model (service + tray split)

```text
┌─────────────────────────────┐        ┌──────────────────────────────┐
│  Agent Service (Windows      │  IPC   │  Tray App (WPF/WinUI)         │
│  Service, always running)    │◄──────►│  system-tray UX, shift        │
│                              │ named  │  buttons, notifications       │
│  - collectors                │ pipe / │                               │
│  - offline queue             │ localhost gRPC                        │
│  - sync + heartbeat          │        └──────────────────────────────┘
│  - policy enforcement        │
│  - auto-update coordinator   │
└─────────────────────────────┘
```

Why split: collection must survive UI crashes/closing (edge cases 2–4). The service holds
the encrypted queue and does all network I/O; the tray app is a thin front end over IPC.

---

## 2. Module map

```text
Agent.Service/
  Auth/            enrollment, device token, request signing (HMAC), token refresh
  Config/          fetch + verify signed policy config; cache; hot-reload
  Time/            server-time sync offset; never trust local clock for truth
  Shift/           local shift view; start/pause/resume/end requests; replay queue
  Collectors/
    IActivityCollector          active window / app usage
    IWebsiteCollector           domain (browser extension / native messaging host)
    IIdleCollector              idle via Win32 GetLastInputInfo
    IInputActivityCollector     aggregate keyboard/mouse % (NO keystrokes)
    IScreenshotCollector        capture per policy; compress; encrypt
  Queue/           SQLite (encrypted) offline buffer; UUID event_id; monotonic sequence
  Sync/            batch uploader (/ingest/events); retry/backoff; idempotency
  Heartbeat/       periodic device heartbeat
  Notifications/   toast notifications
  Update/          check/download/verify-signature/install/restart/report-version
  Ipc/             service ↔ tray channel
Agent.Tray/        WPF/WinUI tray UI (states from spec 17/101)
Agent.Common/      DTOs shared with API contract (doc 03)
```

Collectors are interfaces; Windows implementations register at startup. A macOS/Linux build
provides alternate implementations without touching Sync/Queue/Shift logic.

---

## 3. Tray UI states (spec 17 / 101)

```text
Before shift:  NEXT SHIFT 09:00–18:00 | Clock-in available 08:45 | [ START SHIFT ]
Working:       ● WORKING | Worked 03:42:18 | Break 00:21:32 | Project/Task | [ PAUSE ][ END SHIFT ]
On break:      ● BREAK | Break 00:18:22 | Remaining 00:41:38 | [ RESUME ]
Completed:     SHIFT COMPLETED | Scheduled vs Actual | Worked | Break | Late | Overtime
```
All durations shown are the server's computed values (fetched), not locally calculated truth.

---

## 4. Offline mode & sync (spec 19)

```text
Collectors ─► Queue (encrypted SQLite)
                 │  each event: {event_id (UUID), type, timestamp, payload, sequence}
                 ▼
              Sync: when online, POST /ingest/events in batches (Idempotency-Key)
                 │  server dedupes by event_id; ack advances local high-water mark
                 ▼
              On ack: mark synced; prune; retry unacked with exponential backoff
```
- Lifecycle events (start/break/resume/end) taken offline are queued and replayed in order;
  server validates each against the state machine (doc 04 §6).
- Screenshots: metadata queued; blob uploaded via presign when online; queue holds the local
  encrypted file reference until confirmed.
- Duplicate protection end-to-end via `event_id`.

---

## 5. Collectors — what is and isn't collected (spec 20–24, 45)

| Collector | Collects | Never collects |
|-----------|----------|----------------|
| Application | app/process, window title (if policy permits), start/end/duration | file contents |
| Website | domain (default), URL/category if policy permits | passwords, form data, private messages |
| Idle | idle intervals (threshold from policy) | — |
| Input activity | aggregate keyboard % / mouse % / combined % per interval | actual keystrokes, key content, clipboard |
| Screenshot | image per policy (working-only default); compressed; encrypted; optional watermark | anything when state ≠ WORKING (default) |

Monitoring only runs while the resolved policy says so for the current shift state
(WORKING on; BREAK/PAUSED/COMPLETED off by default). The service enforces this locally but
the server remains authoritative over whether monitoring *should* be active.

---

## 6. Performance budget (spec 59)

- Idle poll via event/timer, not busy-loop.
- Screenshots compressed (JPEG/WebP), uploaded async, off the UI thread.
- Batched network I/O; coalesce app/website events by contiguous focus window.
- Bounded queue size with backpressure; target low CPU/memory footprint.

---

## 7. Security (spec 60)

- TLS with server certificate validation (pinning optional per tenant).
- Device-scoped signing key stored in Windows DPAPI/credential store; requests HMAC-signed.
- Offline queue encrypted at rest (key from DPAPI).
- Config is fetched signed; signature verified before apply (spec 60/96).
- No secrets embedded in the binary; short-lived device tokens refreshed.
- Tamper resistance: service integrity checks; report agent version; server can reject
  outdated versions below `minimum_supported_agent_version`.

---

## 8. Heartbeat (spec 18)

Sent on a fixed cadence with: employee id, device id, current shift id, agent version, OS,
online status, tracking state, timestamp, optional network metadata. Drives presence + the
`monitoring_lost` alert when a required agent goes silent. Not used alone for productivity.

---

## 9. Auto-update (spec 96)

```text
Check (server min/latest version) ─► Download signed package ─► Verify signature
   ─► Install ─► Restart service+tray ─► Report new version via heartbeat
```
Never install an unverified executable. If below minimum supported version, the agent enters
a limited mode and prompts update.

---

## 10. Failure handling (edge cases)

- Screenshot upload fails (13): keep local encrypted file, retry with backoff, surface metric.
- Server unavailable (12): keep buffering; UI shows "syncing pending"; no local truth changes.
- Windows logout/restart (3,4): service resumes on boot; open shift state re-fetched from server.
- Network change (20): sync layer re-establishes; idempotency prevents duplicates.
