# 06 — Frontend Screen Map

Covers spec section 104.9, plus 29–33 (dashboards/analytics), 61–70 (settings/self-service),
84–88 (policy preview/live/viewer/heatmap/trends), 102 (admin experience).

- Stack: Next.js (App Router) + React + TypeScript. Typed API client generated from OpenAPI.
- Every screen is permission-gated (doc 06 RBAC matrix). Screens render server-computed truth;
  the client never computes lateness/worked time.
- Layout: left nav scoped to the user's role; org/team/date context selector in the top bar.

---

## 1. Route tree

```text
/login                              auth (+ /login/2fa, /sso/callback)
/onboarding                         first-run org setup (super/org admin)

/dashboard                          role-aware landing
  ├─ admin overview                 (spec 102: counts, attendance %, avg work, indicator, alerts)
  └─ employee home                  (spec 101: today's shift + start/pause/resume/end)

/live                               live monitoring board (spec 85) — realtime via WS
/employees
  /employees                        table (dept, schedule, shift, status, worked, activity...)
  /employees/[id]                   detail dashboard (spec 30)
  /employees/[id]/timeline          chronological timeline (spec 28)
  /employees/[id]/screenshots       screenshot viewer (spec 86)
  /employees/[id]/applications      per-employee app usage
  /employees/[id]/websites          per-employee domain usage
  /employees/[id]/timesheet         timesheet view

/departments
  /departments                      list
  /departments/[id]/analytics       department analytics (spec 31)
/teams
  /teams                            list
  /teams/[id]                       team dashboard + live status

/attendance                         attendance board + filters (spec 8)
/shifts                             shift explorer (state, scheduled vs actual)
/schedules                          schedule builder (fixed/flexible/rotating/custom)
/leave                              leave requests + approvals
/holidays                          holiday calendars

/projects
  /projects                         list
  /projects/[id]                    tasks + time + costing (costing gated by rate permission)

/timesheets                         approvals queue (manager) / my timesheets (employee)
/corrections                        correction requests + review

/analytics
  /analytics/overview               org analytics
  /analytics/applications           application analytics (spec 32)
  /analytics/websites               website analytics (spec 33)
  /analytics/heatmap                activity heatmap (spec 87)
  /analytics/trends                 trend + comparison (spec 88)
/reports                            build/generate/download + scheduled reports (spec 37/65)

/alerts                             alerts inbox + acknowledge/resolve
/notifications                      notification center

/ai                                 AI assistant: summaries, anomalies, NL questions (RBAC-scoped)

/settings                           admin settings hub (spec 61)
  /settings/organization
  /settings/attendance
  /settings/schedules
  /settings/shift-policies          + policy preview (spec 84)
  /settings/monitoring
  /settings/screenshots
  /settings/applications            classification
  /settings/websites                classification
  /settings/productivity            categories + indicator formula
  /settings/alerts
  /settings/notifications           templates (spec 66)
  /settings/retention               per-data-class retention (spec 82)
  /settings/security                2FA, sessions, SSO
  /settings/devices                 approve/revoke/replace, versions (spec 42/95)
  /settings/projects
  /settings/ai
  /settings/integrations            webhooks, SSO, external systems (spec 78/79)
  /settings/roles                   RBAC role/permission editor

/admin                              platform (super admin only)
  /admin/organizations              tenants
  /admin/health                     health dashboard (spec 94)

/me                                 employee self-service (profile, tz, notifications, my shifts)
```

---

## 2. Key screens (purpose + primary data source)

| Screen | Purpose | Source |
|--------|---------|--------|
| Admin overview | at-a-glance workforce state | `/analytics/overview` |
| Live board | realtime employee status + current app + activity | WS + `/live` |
| Employee detail | schedule/shift/attendance/productivity/apps/sites/screenshots/timeline/projects | `/employees/{id}/dashboard` |
| Timeline | clickable chronological events | `/employees/{id}/timeline` |
| Screenshot viewer | grid + filters + fullscreen; logs every view/download | `/screenshots`, `/screenshots/{id}/url` |
| Heatmap | hour-by-hour activity intensity | `/analytics/heatmap` |
| Trends | current vs previous, entity comparisons | `/analytics/trends` |
| Schedule builder | fixed/flexible/rotating/custom + assignment | `/schedules` |
| Policy editor + preview | edit + see resolved effective policy before save | `/shift-policies`, `/policies/preview` |
| Timesheets | approve/reject/edit-with-reason/lock | `/timesheets` |
| Reports | generate + schedule; CSV/Excel/PDF | `/reports`, `/report-schedules` |
| AI assistant | summaries/anomalies/NL Q&A within scope | `/ai/*` |
| Devices | approve/revoke/replace; version gate | `/devices` |
| Health | API/DB/Redis/workers/agents/queue | `/admin/health` |

---

## 3. Role → default landing & visible nav

| Role | Landing | Nav highlights |
|------|---------|----------------|
| Super Admin | `/admin/organizations` | admin, health, all org tools |
| Org Admin | `/dashboard` (admin overview) | everything within org |
| HR/Admin | `/attendance` | employees, attendance, schedules, leave, reports |
| Manager | `/teams/[own]` | team live/analytics, timesheets, alerts, screenshots (if permitted) |
| Supervisor | `/live` (team-scoped) | limited team monitoring |
| Employee | `/dashboard` (employee home) | my shift, my timesheet, projects/tasks, leave, allowed reports |

Nav items and in-screen actions are filtered by permissions; unauthorized data is never
requested (server also enforces).

---

## 4. Cross-cutting UI concerns

- **Filters (spec 63):** every dashboard supports date / employee / team / department / status /
  project / application / website / productivity category.
- **Global search (spec 64):** employee, team, department, project, task, shift, device.
- **Timezone:** all times displayed in the viewer's effective tz; server sends UTC + tz metadata.
- **Localization (spec 73):** i18n framework from day one; English first; date/time/number formats.
- **Realtime:** live board and dashboards subscribe to WS channels scoped to permission.
- **Privacy visibility (spec 83):** monitoring toggles and policy state visible to admins on the
  relevant settings screens; productivity always labeled "Productivity/Activity Indicator".
