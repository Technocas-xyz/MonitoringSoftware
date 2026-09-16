# Remote Workforce Monitoring — Windows Desktop Agent

Phase 3 of the roadmap (`../docs/08-roadmap-and-dependencies.md`). C#/.NET 8, split into an
always-on **service** (collection, queue, sync) and a **tray** UI, per `../docs/05-desktop-agent.md`.
The agent is a collector and local UX only; **the backend is the source of truth** — the tray
never computes lateness or worked time locally.

## Projects

```
src/Agent.Common    net8.0            DTOs, RequestSigner (HMAC), ApiClient, queue + collector interfaces
src/Agent.Service   net8.0  (Worker)  SQLite offline queue, DPAPI secret store, sync/heartbeat/collection workers
src/Agent.Tray      net8.0-windows    system-tray UI (start/pause/resume/end), reads DPAPI secrets
tests/Agent.Tests   net8.0            signature parity + queue idempotency tests
```

## Build & test

Requires the .NET 8 SDK.

```bash
cd agent
dotnet restore
dotnet build
dotnet test           # cross-platform: signer parity + queue tests
```

`Agent.Tray` targets `net8.0-windows` and only builds/runs on Windows. `Agent.Service` uses
DPAPI (Windows) for at-rest protection.

## Configuration (environment)

```
RWM_API_BASE   default https://localhost:8000
RWM_ORG_SLUG   organization slug (e.g. acme)
RWM_DATA_DIR   default %LOCALAPPDATA%\RwmAgent
```

## Enrollment flow (how a device gets authorized)

1. Employee logs in and the agent (or a setup step) calls `POST /api/v1/auth/agent/enroll`
   with the user's access token -> a **pending** device is created.
2. An admin approves it: `POST /api/v1/devices/{id}/approve`. The response returns a
   **signing secret exactly once**. Provision it to the device's secret store as `signing_secret`,
   along with `device_id` and `employee_id`.
3. The agent exchanges a signed proof for a device token: `POST /api/v1/auth/agent/token`
   (`RequestSigner` signs `device_id`). Store the returned `device_token`.

After that, every agent request carries `Authorization: Bearer <device_token>` plus
`X-Signature`/`X-Timestamp` (HMAC over method+path+body+timestamp). The server verifies the
signature against the device's secret and rejects stale timestamps.

## Secret store keys (DPAPI, per current user)

```
device_id        the enrolled device's UUID
employee_id      the linked employee UUID
device_token     JWT (type=device) from /auth/agent/token
signing_secret   HMAC secret from device approval
```

## Offline behavior

Collectors enqueue events to an encrypted local SQLite queue with a client-generated
`event_id` (GUID) and a monotonic sequence. `SyncWorker` drains the queue in idempotent
batches; on network failure it backs off and retries. The server dedupes by `event_id`, so
re-sending an un-acked batch never double-counts (spec 19, docs/05 §4).

## Collectors (Phase 4)

Concrete Windows collectors are implemented and registered in `Agent.Service` (Windows only):

- **ActiveWindowCollector** — foreground app/process and (policy-permitting) window title,
  emitting `APPLICATION_ACTIVITY`; derives a best-effort domain from browser titles for
  `WEBSITE_ACTIVITY`. Reliable per-tab URLs need a browser extension (doc 00 A2).
- **ActivityCollector** + **WindowsInputCounter** — aggregate keyboard/mouse activity as a
  0–100 percentage and `IDLE` detection. The input hooks **count events only**; they never
  read key codes, characters, clipboard, or coordinates.
- **ScreenshotCollector** — captures per `screenshot_mode`/interval, JPEG-compressed, uploaded
  out-of-band via presign → PUT → confirm (never queued in plaintext).

Collectors run only while the server-reported shift state is `WORKING`. Pure helper logic
(`ActivityMath.Percent`, `DomainParser.FromTitle`) lives in `Agent.Common` and is unit-tested
cross-platform in `Agent.Tests`.

## Privacy (enforced in collectors)

Collectors never capture keystroke content, clipboard, passwords, private messages, or auth
tokens. Only aggregate keyboard/mouse activity and policy-permitted metadata are collected,
and only while the server-reported shift state is `WORKING` (default).

## Not runnable in this authoring environment

These sources were authored and reviewed without a .NET SDK available here, so they have
**not been compiled or run** in this workspace. Build and test on a machine with the .NET 8
SDK using the commands above.
