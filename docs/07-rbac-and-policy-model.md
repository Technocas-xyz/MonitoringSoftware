# 07 — RBAC Permission Matrix & Monitoring-Policy Model

Covers spec section 104.10 and 104.11, plus 44 (roles), 7 (policy inheritance), 26/83 (monitoring).

---

## PART A — RBAC

### 1. Roles (spec 44)

| Role key | Scope | Summary |
|----------|-------|---------|
| `super_admin` | platform | full platform + all tenants |
| `org_admin` | organization | full access within one org |
| `hr` | organization | employees, schedules, attendance, leave, reports |
| `manager` | team(s) | monitor + manage assigned team(s) |
| `supervisor` | team(s) | limited team monitoring (read-mostly) |
| `employee` | self | own shifts/timesheets/allowed reports |

Roles are assigned with a **scope** (`organization` / `department` / `team` + id) via
`user_roles`, so a manager can be bound to specific teams.

### 2. Permission keys (granular — spec 44)

```text
# directory
employee.view  employee.manage   department.manage   team.manage   user.manage   role.manage
# devices
device.view    device.approve    device.revoke
# scheduling / policy
schedule.view  schedule.manage    shiftpolicy.manage  monitoringpolicy.manage
leave.view     leave.approve      holiday.manage
# shifts / attendance
shift.view     shift.start_own    shift.control_own   shift.force_stop
attendance.view
# monitoring data
activity.view  application.view   website.view
screenshot.view  screenshot.download
# productivity
classification.manage  productivity.manage
# projects / timesheets
project.view   project.manage     task.time_track
timesheet.view timesheet.approve  timesheet.edit   correction.review
rate.view      rate.manage        # salary/rate — highly restricted
# alerts / reports / analytics
alert.view     alert.manage       report.view   report.manage
analytics.view analytics.org
# ai / audit / settings / integrations
ai.use         audit.view         settings.manage  integration.manage  webhook.manage
# platform
org.manage     platform.admin
```

### 3. Permission matrix (default grants)

Legend: ✔ full, ● scoped (own team/self only), — none.

| Permission | super | org_admin | hr | manager | supervisor | employee |
|------------|:----:|:---------:|:--:|:-------:|:----------:|:--------:|
| employee.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| employee.manage | ✔ | ✔ | ✔ | — | — | — |
| department.manage / team.manage | ✔ | ✔ | ● | — | — | — |
| user.manage / role.manage | ✔ | ✔ | — | — | — | — |
| device.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| device.approve / revoke | ✔ | ✔ | ✔ | — | — | — |
| schedule.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| schedule.manage | ✔ | ✔ | ✔ | ● (if allowed) | — | — |
| shiftpolicy.manage / monitoringpolicy.manage | ✔ | ✔ | — | — | — | — |
| leave.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| leave.approve | ✔ | ✔ | ✔ | ● team | — | — |
| shift.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| shift.start_own / control_own | — | — | — | — | — | ✔ |
| shift.force_stop | ✔ | ✔ | ● | ● team | — | — |
| attendance.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| activity.view / application.view / website.view | ✔ | ✔ | ● | ● team | ● team | ● self (if allowed) |
| screenshot.view | ✔ | ✔ | ● | ● team (if permitted) | — | ● self (if allowed) |
| screenshot.download | ✔ | ✔ | — | ● (if permitted) | — | — |
| classification.manage / productivity.manage | ✔ | ✔ | — | — | — | — |
| project.view | ✔ | ✔ | ✔ | ● team | ● team | ● assigned |
| project.manage | ✔ | ✔ | ● | ● (if allowed) | — | — |
| task.time_track | — | — | — | ● | ● | ✔ |
| timesheet.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| timesheet.approve / edit / correction.review | ✔ | ✔ | ✔ | ● team | — | — |
| rate.view / rate.manage | ✔ | ✔ (view) | — | — | — | — |
| alert.view | ✔ | ✔ | ✔ | ● team | ● team | — |
| alert.manage | ✔ | ✔ | ● | ● team (if allowed) | — | — |
| report.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| report.manage | ✔ | ✔ | ✔ | — | — | — |
| analytics.view | ✔ | ✔ | ✔ | ● team | ● team | ● self |
| analytics.org | ✔ | ✔ | ✔ | — | — | — |
| ai.use | ✔ | ✔ | ✔ | ● team scope | ● team scope | — |
| audit.view | ✔ | ✔ | ● | — | — | — |
| settings.manage / integration.manage / webhook.manage | ✔ | ✔ | — | — | — | — |
| org.manage | ✔ | ✔ | — | — | — | — |
| platform.admin | ✔ | — | — | — | — | — |

`rate.view`/`rate.manage` gate all salary/costing/payroll data (spec 76/77).
Roles and per-permission grants are editable in `/settings/roles`; the matrix above is the seed.

### 4. Enforcement (spec 90/100)

- Server checks permission **and** scope on every request; scope narrows the data set
  (e.g. manager queries auto-filtered to their team ids).
- Postgres RLS additionally guarantees tenant isolation.
- AI runs strictly within the caller's resolved scope; it cannot read data the caller can't.
- Client authz (nav/buttons) is UX only; never trusted.

---

## PART B — Monitoring & Shift Policy Model

### 5. Policy inheritance (spec 7)

```text
Organization ─► Department ─► Team ─► Employee     (most specific wins)
```
Resolution algorithm for a given employee + date:
1. Collect `policy_assignments` for the employee's org, department, team, and the employee.
2. Order by specificity: employee > team > department > organization; tie-break by `priority`.
3. Start from the org-level policy; for each more specific level, **override only if that level
   is permitted to override** (`allow_override` on the assignment) — otherwise the inherited
   value stands.
4. Produce a single **resolved effective policy** (shift + monitoring) — this is what
   `/policies/preview` returns and what gets **frozen onto the shift** at start (doc 04).

An employee may override inherited settings **only if** the assignment above them set
`allow_override = true` (spec 7).

### 6. Shift policy fields (resolved)

From `shift_policies` (doc 02): tracking_mode, earliest/latest clock-in, late_threshold,
allow_break, max_break, allow_multiple_breaks, allow_early_clockout, allow_overtime +
approval, auto_start, auto_end, monitoring_required.

### 7. Monitoring policy fields (resolved)

From `monitoring_policies`: monitor_applications, monitor_websites + website_mode
(domain|category|full_url), monitor_idle + idle_threshold + idle_classification
(idle|break|working, default idle), monitor_kbd_mouse (aggregate only), screenshot_mode
(off|interval|random) + interval + capture_scope (working_only|entire_shift|active_use) +
watermark.

Screenshot default by shift state (spec 24): WORKING on; BREAK/PAUSED/COMPLETED off.

### 8. Privacy toggles are first-class (spec 83)

Each monitoring dimension is independently switchable per policy: screenshots, websites,
applications, idle, keyboard/mouse (aggregate), domain-only. All visible to admins in
`/settings/monitoring`. Hard prohibitions (never collected) are enforced in the agent
collectors regardless of policy: passwords, keystroke content, clipboard, private messages,
auth tokens.

### 9. Policy preview (spec 84)

`/policies/preview` returns the resolved effective policy plus a human-readable summary
(shift window, clock-in window, late-after time, break rules, screenshot cadence, monitored
dimensions, idle threshold, auto-end) so admins confirm exactly what will apply before saving.

### 10. Per-scope classification (spec 26)

Productivity classification is resolved with the same specificity rule (employee's team/dept),
so the same app/domain can be productive for one department and unproductive for another.
The productivity indicator formula is configurable per org (category weights) and always
surfaced as an **indicator**, never an absolute performance score (spec 27).
