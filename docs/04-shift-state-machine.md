# 04 — Shift State Machine Specification

Covers spec section 104.7, plus 5 (state machine), 4 (tracking modes), 6/7 (schedules/policies),
10–14 (start/pause/resume/end/auto), 100 (server authority).

**The backend owns all state.** The client requests transitions; the server validates against
the shift's frozen policy snapshot and server time, then records an authoritative `shift_event`.

---

## 1. States

```text
SCHEDULED       created for a scheduled slot; not yet startable
AVAILABLE       within clock-in window; employee may start
WORKING         active shift, monitoring enabled per policy
ON_BREAK        employee-initiated break (break record open)
PAUSED          non-break pause (policy-defined; monitoring may stop)
COMPLETED       ended by employee (manual end)
AUTO_COMPLETED  ended by system (auto_end policy)
MISSED          never started within window (missed shift)
FORCE_STOPPED   ended by manager/admin
CANCELLED       cancelled before start (e.g. approved leave/holiday)
```

`WORKING`, `ON_BREAK`, `PAUSED`, `AVAILABLE` are the "active" set enforced by the
one-active-shift-per-employee partial unique index (doc 02).

---

## 2. Transition diagram

```text
                 (scheduler: at window open)
   SCHEDULED ───────────────────────────────► AVAILABLE
       │                                          │
       │ (no start within window)                 │ start (employee)  / AUTO_START (system)
       ▼                                          ▼
     MISSED                                    WORKING ◄────────────────┐
       ▲                                       │  │  │                  │
       │ (leave/holiday added)                 │  │  │ resume           │ resume
   SCHEDULED ──► CANCELLED                      │  │  └──► PAUSED ───────┘
                                                │  │
                                                │  └──────► ON_BREAK ────┐
                                                │            (break)     │ resume (break end)
                                                │                        │
                                                │ ◄──────────────────────┘
                                                │
                 end (employee)  ┌──────────────┼──────────────┐  AUTO_END (system)
                                 ▼              ▼               ▼
                            COMPLETED    FORCE_STOPPED    AUTO_COMPLETED
                                          (manager/admin)
```

---

## 3. Transition table (guards + effects)

| From | Event | To | Guard (server-validated) | Effect |
|------|-------|----|--------------------------|--------|
| SCHEDULED | window opens | AVAILABLE | server time ≥ (scheduled_start − earliest_clock_in) | (scheduler) mark available |
| SCHEDULED | scheduler: window closed, never started | MISSED | server time > latest_clock_in and no start | write MISSED; alert `missed_shift` |
| SCHEDULED | leave/holiday applies | CANCELLED | approved leave or holiday covers date | write CANCELLED; no attendance violation |
| AVAILABLE | start | WORKING | employee active+authorized; within window; no other active shift; device approved; policy permits; tz applied | freeze policy snapshot; write SHIFT_START; compute late_seconds; enable monitoring |
| AVAILABLE | AUTO_START | WORKING | policy.auto_start; server time ≥ scheduled_start | write AUTO_START; enable monitoring |
| AVAILABLE | scheduler: window closed | MISSED | server time > latest_clock_in | write MISSED; alert |
| WORKING | pause (break) | ON_BREAK | policy.allow_break; max_breaks not exceeded; break rules ok | open break record; write BREAK_START; stop monitoring if policy says so |
| WORKING | pause (non-break) | PAUSED | policy permits pause | write PAUSE; monitoring per policy |
| WORKING | end | COMPLETED | employee has active shift; policy.allow_early_clockout OR at/after scheduled_end | write SHIFT_END; stop monitoring; compute durations |
| WORKING | AUTO_END | AUTO_COMPLETED | policy.auto_end; server time ≥ scheduled_end (+ overtime rules) | write AUTO_END; stop monitoring; compute durations |
| WORKING | force-stop | FORCE_STOPPED | actor is manager/admin with permission | write FORCE_STOP (actor, reason); stop monitoring |
| ON_BREAK | resume | WORKING | shift is ON_BREAK; authorized | close break; write BREAK_END + RESUME; resume monitoring; flag exceeded if over max |
| ON_BREAK | AUTO_END | AUTO_COMPLETED | policy.auto_end at scheduled_end | close break; write AUTO_END |
| PAUSED | resume | WORKING | shift is PAUSED; authorized | write RESUME; resume monitoring |
| PAUSED | end / AUTO_END / force-stop | COMPLETED/AUTO_COMPLETED/FORCE_STOPPED | as above | as above |

Any event not in this table for the current state → `409 shift.invalid_transition`
returning the current state. **Terminal states** (COMPLETED, AUTO_COMPLETED, MISSED,
FORCE_STOPPED, CANCELLED) accept no further transitions.

---

## 4. Tracking modes → which transitions the client may trigger (spec 4)

| Mode | start | pause/break | resume | end | auto start | auto end |
|------|:-----:|:-----------:|:------:|:---:|:----------:|:--------:|
| A Flexible (employee-controlled) | employee | employee | employee | employee | — | — |
| B Scheduled + employee start | employee (window-gated) | employee | employee | employee | — | optional |
| C Fully enforced | system | policy | policy | system | yes | yes |
| D Hybrid (default) | employee (window-gated) | employee | employee | employee (early-out gated) | — | yes |

The mode comes from the resolved shift policy snapshot on the shift; the server enforces it
regardless of what the client sends.

---

## 5. Computed fields on transition (server, from server time)

On `SHIFT_START`:
```text
late_seconds = max(0, actual_start - scheduled_start - late_threshold_grace?)  # per policy
```
On end (COMPLETED / AUTO_COMPLETED / FORCE_STOPPED):
```text
worked_seconds   = Σ(WORKING intervals)                      # excludes breaks & idle-as-idle
break_seconds    = Σ(break durations)
idle_seconds     = Σ(idle intervals) classified per policy
early_leave_secs = max(0, scheduled_end - actual_end)  (if ended before scheduled_end)
overtime_seconds = max(0, actual_end - scheduled_end)  (if allow_overtime; approval per policy)
```
Attendance status (doc 02 `attendance`) is then derived (PRESENT/LATE/OVERTIME/EARLY_LEAVE/etc.).

---

## 6. Concurrency & integrity

- **Single active shift:** partial unique index blocks a second active shift (edge case 8).
- **Optimistic locking:** `shifts.updated_at`/version checked on transition; concurrent
  conflicting transitions get `409 shift.conflict`, client re-reads.
- **Idempotent transitions:** each transition carries an `event_id`; replay (offline sync)
  matching an existing `shift_events.event_key` is a no-op returning current state.
- **Offline replay ordering:** buffered lifecycle events replay in device `sequence` order;
  the server still validates each against the resulting state and reconciles times.

---

## 7. Edge-case handling (spec 81 mapped to state machine)

| Edge case | Handling |
|-----------|----------|
| 1 Internet lost | agent buffers; on reconnect replays lifecycle events idempotently |
| 2 Agent closed / 3 restart / 4 Windows logout | heartbeat gap → presence OFFLINE; shift stays in last server state; `monitoring_lost` alert if required |
| 5 Clock changed | server time authoritative; client_time advisory only |
| 6 Timezone changed | shift tz frozen at creation; recomputation uses snapshot |
| 7 Multiple devices | shift not device-bound; any approved device may drive it; events carry device_id |
| 8 Two shifts | blocked by unique index → `409 shift.already_active` |
| 9 Start before window | `422 shift.window_not_open` |
| 10 Stay after end | overtime per policy; or AUTO_END if configured |
| 11 Break too long | `exceeded=true` on break; alert; auto-resume optional per policy |
| 12 Server unavailable | agent keeps buffering; no client-side truth |
| 16 Terminated mid-shift | admin force-stop → FORCE_STOPPED; device revoked |
| 17 Schedule change mid-shift | active shift keeps its snapshot; change applies to future shifts |
| 18 Holiday added after creation | future SCHEDULED shifts → CANCELLED; active/past unaffected |

---

## 8. Every automatic operation is audited (spec 14/46)

AUTO_START, AUTO_END, MISSED marking, CANCELLED-by-holiday, and FORCE_STOP each write both a
`shift_event` (source=system|manager) and an `audit_logs` row with actor, old/new state, reason.
