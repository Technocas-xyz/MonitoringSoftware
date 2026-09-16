# 02 — Database ERD and Complete Schema

Covers spec section 104.4 and 104.5, plus 43 (multi-tenant), 53 (tables), 54 (data-model
principle), 55 (storage), 82 (retention).

- Engine: **PostgreSQL 15+**
- Tenant isolation: every tenant-owned row carries `organization_id`; **Row-Level Security**
  policies filter on a session GUC `app.current_org`.
- IDs: UUID v7 (time-ordered) primary keys unless noted.
- Timestamps: `timestamptz`, stored UTC.
- High-volume tables: declared `PARTITION BY RANGE (occurred_at)` (monthly).
- Money/rates: `numeric(12,2)`. Durations: integer **seconds**.

---

## 1. ERD (logical)

```text
organizations ─┬─< departments ─< teams ─< employees
               │                              │
               ├─< users >── employee_users ──┤        (a user may be linked to an employee)
               │                              │
               ├─< roles ─< role_permissions >── permissions
               │      └────< user_roles >── users
               │
               ├─< devices >──────────────────┤ (device belongs to employee)
               │
               ├─< work_schedules ─< schedule_assignments >── (employee|team|dept)
               ├─< shift_policies    ────────< policy_assignments >── (org|dept|team|employee)
               ├─< monitoring_policies ──────< policy_assignments >
               │
               ├─< holidays        (holiday_calendars ─< holiday_days)
               ├─< leave_requests ─── employee
               │
               ├─< shifts ─┬─< shift_events
               │           ├─< breaks
               │           └── (1:1 derived) attendance
               │
               ├─< application_events   (partitioned)   ─ shift, employee, device
               ├─< website_events       (partitioned)
               ├─< activity_intervals   (partitioned)
               ├─< screenshots          (partitioned; metadata only)
               │
               ├─< productivity_categories ─< application_classifications
               │                            └─< website_classifications   (scope: org|dept|team)
               │
               ├─< projects ─< tasks ─< task_time_entries ─ shift/employee
               ├─< timesheets ─< timesheet_entries ─< timesheet_corrections
               │
               ├─< alert_rules ─< alerts
               ├─< notifications  (+ notification_templates)
               ├─< report_schedules
               ├─< webhooks ─< webhook_deliveries
               ├─< ai_jobs / ai_summaries / ai_anomalies
               └─< audit_logs   (append-only, partitioned)
```

Data-model principle (spec 54): **attendance is derived** from `shifts` + `shift_events`;
it is a computed/cached projection, never the primary event store.

---

## 2. Core tenancy, identity, RBAC

```sql
CREATE TABLE organizations (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    name            text NOT NULL,
    slug            text NOT NULL UNIQUE,
    timezone        text NOT NULL DEFAULT 'UTC',          -- IANA tz
    locale          text NOT NULL DEFAULT 'en',
    status          text NOT NULL DEFAULT 'active',       -- active|suspended
    settings        jsonb NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           text NOT NULL,
    password_hash   text,                                 -- null if SSO-only
    full_name       text NOT NULL,
    status          text NOT NULL DEFAULT 'active',       -- active|disabled|invited
    twofa_enabled   boolean NOT NULL DEFAULT false,
    twofa_secret    text,                                 -- encrypted
    sso_subject     text,                                 -- oidc/saml subject
    timezone        text,                                 -- overrides org tz
    last_login_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, email)
);

CREATE TABLE roles (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid REFERENCES organizations(id) ON DELETE CASCADE, -- null = platform role
    key             text NOT NULL,        -- super_admin|org_admin|hr|manager|supervisor|employee
    name            text NOT NULL,
    is_system       boolean NOT NULL DEFAULT false,
    UNIQUE (organization_id, key)
);

CREATE TABLE permissions (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    key             text NOT NULL UNIQUE, -- e.g. 'shift.view', 'screenshot.download'
    description     text NOT NULL
);

CREATE TABLE role_permissions (
    role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id   uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id         uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    scope_type      text NOT NULL DEFAULT 'organization', -- organization|department|team
    scope_id        uuid,                                 -- dept/team id when scoped
    PRIMARY KEY (user_id, role_id, scope_type, scope_id)
);
```

## 3. Org structure & employees

```sql
CREATE TABLE departments (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    parent_id       uuid REFERENCES departments(id),      -- optional nesting
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE teams (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    department_id   uuid REFERENCES departments(id) ON DELETE SET NULL,
    name            text NOT NULL,
    manager_user_id uuid REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE employees (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         uuid REFERENCES users(id) ON DELETE SET NULL, -- login identity
    department_id   uuid REFERENCES departments(id) ON DELETE SET NULL,
    team_id         uuid REFERENCES teams(id) ON DELETE SET NULL,
    employee_code   text,
    full_name       text NOT NULL,
    timezone        text,                                 -- overrides team/org
    hourly_rate     numeric(12,2),                        -- restricted access (costing/payroll)
    status          text NOT NULL DEFAULT 'active',       -- active|inactive|terminated
    hired_at        date,
    terminated_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, employee_code)
);
CREATE INDEX ix_employees_org_team ON employees(organization_id, team_id);
CREATE INDEX ix_employees_org_dept ON employees(organization_id, department_id);
```

## 4. Devices

```sql
CREATE TABLE devices (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    hostname        text,
    os              text,                                 -- windows|macos|linux
    os_version      text,
    agent_version   text,
    signing_key_id  text,                                 -- ref to per-device signing key
    status          text NOT NULL DEFAULT 'pending',      -- pending|approved|revoked
    last_seen_at    timestamptz,
    approved_at     timestamptz,
    revoked_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_devices_employee ON devices(organization_id, employee_id);
```

## 5. Scheduling, policies, holidays, leave

```sql
CREATE TABLE work_schedules (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    type            text NOT NULL,        -- fixed|flexible|rotating|custom
    timezone        text,                 -- schedule tz (defaults to employee/org)
    definition      jsonb NOT NULL,       -- see note below
    created_at      timestamptz NOT NULL DEFAULT now()
);
-- definition examples:
--  fixed:    {"days":{"mon":["09:00","18:00"], ... }}
--  flexible: {"required_seconds":28800,"window":["07:00","20:00"]}
--  rotating: {"cycle_weeks":2,"weeks":[{...},{...}]}
--  multiple: {"days":{"mon":[["08:00","12:00"],["14:00","18:00"]]}}

CREATE TABLE schedule_assignments (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    schedule_id     uuid NOT NULL REFERENCES work_schedules(id) ON DELETE CASCADE,
    target_type     text NOT NULL,        -- employee|team|department
    target_id       uuid NOT NULL,
    effective_from  date NOT NULL,
    effective_to    date,
    priority        int NOT NULL DEFAULT 0
);
CREATE INDEX ix_sched_assign_target ON schedule_assignments(organization_id, target_type, target_id);

CREATE TABLE shift_policies (
    id                   uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name                 text NOT NULL,
    tracking_mode        text NOT NULL DEFAULT 'hybrid',  -- flexible|scheduled_start|enforced|hybrid
    earliest_clock_in_min int,             -- minutes before scheduled start
    latest_clock_in_min   int,             -- minutes after scheduled start
    late_threshold_min    int NOT NULL DEFAULT 15,
    allow_break           boolean NOT NULL DEFAULT true,
    max_break_seconds     int,
    allow_multiple_breaks boolean NOT NULL DEFAULT true,
    allow_early_clockout  boolean NOT NULL DEFAULT false,
    allow_overtime        boolean NOT NULL DEFAULT true,
    overtime_requires_approval boolean NOT NULL DEFAULT true,
    auto_start            boolean NOT NULL DEFAULT false,
    auto_end              boolean NOT NULL DEFAULT true,
    monitoring_required   boolean NOT NULL DEFAULT true,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE monitoring_policies (
    id                   uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name                 text NOT NULL,
    monitor_applications boolean NOT NULL DEFAULT true,
    monitor_websites     boolean NOT NULL DEFAULT true,
    website_mode         text NOT NULL DEFAULT 'domain',  -- domain|category|full_url
    monitor_idle         boolean NOT NULL DEFAULT true,
    idle_threshold_seconds int NOT NULL DEFAULT 600,
    idle_classification  text NOT NULL DEFAULT 'idle',    -- idle|break|working
    monitor_kbd_mouse    boolean NOT NULL DEFAULT true,   -- aggregate only
    screenshot_mode      text NOT NULL DEFAULT 'off',     -- off|interval|random
    screenshot_interval_seconds int,
    screenshot_capture_scope text NOT NULL DEFAULT 'working_only', -- working_only|entire_shift|active_use
    screenshot_watermark boolean NOT NULL DEFAULT false,
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- One assignment table for both policy kinds via polymorphic target + policy_kind
CREATE TABLE policy_assignments (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    policy_kind     text NOT NULL,        -- shift|monitoring
    policy_id       uuid NOT NULL,
    target_type     text NOT NULL,        -- organization|department|team|employee
    target_id       uuid NOT NULL,
    allow_override  boolean NOT NULL DEFAULT false,
    priority        int NOT NULL DEFAULT 0
);
CREATE INDEX ix_policy_assign ON policy_assignments(organization_id, policy_kind, target_type, target_id);

CREATE TABLE holiday_calendars (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    country         text, region text
);
CREATE TABLE holiday_days (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    calendar_id     uuid NOT NULL REFERENCES holiday_calendars(id) ON DELETE CASCADE,
    day             date NOT NULL,
    name            text NOT NULL,
    UNIQUE (calendar_id, day)
);

CREATE TABLE leave_requests (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    type            text NOT NULL,        -- annual|sick|casual|custom
    start_date      date NOT NULL,
    end_date        date NOT NULL,
    status          text NOT NULL DEFAULT 'pending', -- pending|approved|rejected|cancelled
    reason          text,
    approver_user_id uuid REFERENCES users(id),
    decided_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_leave_emp ON leave_requests(organization_id, employee_id, start_date);
```

## 6. Shifts, events, breaks, attendance (authoritative core)

```sql
CREATE TABLE shifts (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id         uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    schedule_id         uuid REFERENCES work_schedules(id),
    state               text NOT NULL,   -- see doc 04 (SCHEDULED..CANCELLED)
    scheduled_start     timestamptz,
    scheduled_end       timestamptz,
    actual_start        timestamptz,
    actual_end          timestamptz,
    timezone            text NOT NULL,   -- effective tz snapshot
    policy_snapshot     jsonb NOT NULL,  -- shift+monitoring policy frozen at creation/start
    schedule_snapshot   jsonb,           -- schedule window frozen
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
-- Enforce one active shift per employee (partial unique index)
CREATE UNIQUE INDEX uq_active_shift_per_employee
    ON shifts (organization_id, employee_id)
    WHERE state IN ('WORKING','ON_BREAK','PAUSED','AVAILABLE');
CREATE INDEX ix_shifts_emp_start ON shifts(organization_id, employee_id, scheduled_start);

CREATE TABLE shift_events (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shift_id        uuid NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    type            text NOT NULL,   -- SHIFT_START|BREAK_START|BREAK_END|RESUME|SHIFT_END|AUTO_START|AUTO_END|FORCE_STOP
    occurred_at     timestamptz NOT NULL,          -- server-authoritative time
    client_time     timestamptz,                   -- advisory
    source          text NOT NULL,   -- employee|system|manager
    actor_user_id   uuid REFERENCES users(id),
    device_id       uuid REFERENCES devices(id),
    metadata        jsonb NOT NULL DEFAULT '{}',
    event_key       text NOT NULL,                 -- idempotency
    UNIQUE (organization_id, event_key)
);
CREATE INDEX ix_shift_events_shift ON shift_events(shift_id, occurred_at);

CREATE TABLE breaks (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    shift_id        uuid NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz,
    max_seconds     int,
    paid            boolean NOT NULL DEFAULT false,
    exceeded        boolean NOT NULL DEFAULT false,
    approved_by     uuid REFERENCES users(id)
);
CREATE INDEX ix_breaks_shift ON breaks(shift_id);

-- Derived projection (1:1 with a completed/derivable shift day)
CREATE TABLE attendance (
    id                  uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id         uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    shift_id            uuid REFERENCES shifts(id) ON DELETE SET NULL,
    work_date           date NOT NULL,
    status              text NOT NULL,   -- PRESENT|LATE|ABSENT|PARTIAL|EARLY_LEAVE|OVERTIME|ON_LEAVE|HOLIDAY|REST_DAY|MISSED_SHIFT
    scheduled_start     timestamptz, scheduled_end timestamptz,
    actual_start        timestamptz, actual_end   timestamptz,
    worked_seconds      int NOT NULL DEFAULT 0,
    break_seconds       int NOT NULL DEFAULT 0,
    idle_seconds        int NOT NULL DEFAULT 0,
    late_seconds        int NOT NULL DEFAULT 0,
    early_leave_seconds int NOT NULL DEFAULT 0,
    overtime_seconds    int NOT NULL DEFAULT 0,
    computed_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, employee_id, work_date)
);
CREATE INDEX ix_attendance_org_date ON attendance(organization_id, work_date);
```

## 7. Monitoring data (partitioned, high-volume)

```sql
CREATE TABLE application_events (
    id              uuid DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    employee_id     uuid NOT NULL,
    device_id       uuid NOT NULL,
    shift_id        uuid,
    application     text NOT NULL,
    process_name    text,
    window_title    text,               -- only if policy permits
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz,
    duration_seconds int NOT NULL,
    occurred_at     timestamptz NOT NULL,        -- partition key (= started_at)
    event_key       text NOT NULL,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (organization_id, event_key, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX ix_appev_emp ON application_events(organization_id, employee_id, occurred_at);

CREATE TABLE website_events (
    id              uuid DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    employee_id     uuid NOT NULL,
    device_id       uuid NOT NULL,
    shift_id        uuid,
    domain          text NOT NULL,
    url             text,               -- only if website_mode = full_url
    category        text,
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz,
    duration_seconds int NOT NULL,
    occurred_at     timestamptz NOT NULL,
    event_key       text NOT NULL,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (organization_id, event_key, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX ix_webev_emp ON website_events(organization_id, employee_id, occurred_at);

CREATE TABLE activity_intervals (
    id              uuid DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    employee_id     uuid NOT NULL,
    device_id       uuid NOT NULL,
    shift_id        uuid,
    interval_start  timestamptz NOT NULL,
    interval_end    timestamptz NOT NULL,
    keyboard_pct    smallint,           -- 0..100 aggregate
    mouse_pct       smallint,
    combined_pct    smallint,
    is_idle         boolean NOT NULL DEFAULT false,
    occurred_at     timestamptz NOT NULL,
    event_key       text NOT NULL,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (organization_id, event_key, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX ix_actint_emp ON activity_intervals(organization_id, employee_id, occurred_at);

CREATE TABLE screenshots (
    id              uuid DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    employee_id     uuid NOT NULL,
    device_id       uuid NOT NULL,
    shift_id        uuid,
    storage_key     text NOT NULL,      -- object storage path (blob NOT in Postgres)
    thumb_key       text,
    captured_at     timestamptz NOT NULL,
    width int, height int, bytes int,
    watermarked     boolean NOT NULL DEFAULT false,
    encryption_key_id text NOT NULL,
    retention_until date,               -- set from retention policy
    occurred_at     timestamptz NOT NULL,
    event_key       text NOT NULL,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (organization_id, event_key, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX ix_shots_emp ON screenshots(organization_id, employee_id, occurred_at);

CREATE TABLE screenshot_access_log (   -- spec 86: log every view/download
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    screenshot_id   uuid NOT NULL,
    actor_user_id   uuid NOT NULL,
    action          text NOT NULL,      -- view|download
    at              timestamptz NOT NULL DEFAULT now(),
    ip              inet
);
```

## 8. Productivity classification

```sql
CREATE TABLE productivity_categories (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key             text NOT NULL,      -- productive|neutral|unproductive (extensible)
    label           text NOT NULL,
    weight          numeric(4,2) NOT NULL DEFAULT 0, -- used by indicator formula
    UNIQUE (organization_id, key)
);

-- Classification is scoped so the same app/site can differ per dept/team (spec 26)
CREATE TABLE application_classifications (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    application     text NOT NULL,
    category_id     uuid NOT NULL REFERENCES productivity_categories(id),
    scope_type      text NOT NULL DEFAULT 'organization', -- organization|department|team
    scope_id        uuid,
    UNIQUE (organization_id, application, scope_type, scope_id)
);
CREATE TABLE website_classifications (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    domain          text NOT NULL,
    category_id     uuid NOT NULL REFERENCES productivity_categories(id),
    scope_type      text NOT NULL DEFAULT 'organization',
    scope_id        uuid,
    UNIQUE (organization_id, domain, scope_type, scope_id)
);
```

## 9. Projects, tasks, timesheets

```sql
CREATE TABLE projects (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    code            text,
    status          text NOT NULL DEFAULT 'active',
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tasks (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id      uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            text NOT NULL,
    status          text NOT NULL DEFAULT 'open'
);
CREATE TABLE task_time_entries (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    task_id         uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    shift_id        uuid REFERENCES shifts(id) ON DELETE SET NULL,
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz,
    duration_seconds int,
    source          text NOT NULL DEFAULT 'agent' -- agent|manual
);
CREATE INDEX ix_tte_emp ON task_time_entries(organization_id, employee_id, started_at);

CREATE TABLE timesheets (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    employee_id     uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    period_start    date NOT NULL,
    period_end      date NOT NULL,
    status          text NOT NULL DEFAULT 'draft', -- draft|submitted|approved|rejected|locked
    approved_by     uuid REFERENCES users(id),
    approved_at     timestamptz,
    UNIQUE (organization_id, employee_id, period_start, period_end)
);
CREATE TABLE timesheet_entries (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    timesheet_id    uuid NOT NULL REFERENCES timesheets(id) ON DELETE CASCADE,
    work_date       date NOT NULL,
    scheduled_seconds int, worked_seconds int, break_seconds int, overtime_seconds int,
    status          text
);
CREATE TABLE timesheet_corrections (   -- spec 39/70; every change audited separately too
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    timesheet_id    uuid REFERENCES timesheets(id),
    entry_id        uuid REFERENCES timesheet_entries(id),
    request_type    text NOT NULL,      -- missed_clockin|incorrect_clockout|incorrect_break|wrong_project|wrong_task
    old_value       jsonb, new_value jsonb,
    reason          text NOT NULL,
    status          text NOT NULL DEFAULT 'pending', -- pending|approved|rejected
    requested_by    uuid NOT NULL REFERENCES users(id),
    approver_user_id uuid REFERENCES users(id),
    decided_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

## 10. Alerts, notifications, reports, webhooks, AI

```sql
CREATE TABLE alert_rules (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key             text NOT NULL,      -- late_arrival|excessive_idle|excessive_unproductive|missed_shift|monitoring_lost|early_departure
    enabled         boolean NOT NULL DEFAULT true,
    severity        text NOT NULL DEFAULT 'warning', -- info|warning|critical
    scope_type      text NOT NULL DEFAULT 'organization',
    scope_id        uuid,
    params          jsonb NOT NULL DEFAULT '{}',      -- thresholds
    channels        jsonb NOT NULL DEFAULT '["in_app"]'
);
CREATE TABLE alerts (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    rule_id         uuid REFERENCES alert_rules(id),
    employee_id     uuid REFERENCES employees(id),
    severity        text NOT NULL,
    message         text NOT NULL,
    context         jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'open',     -- open|acknowledged|resolved
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_alerts_org_created ON alerts(organization_id, created_at);

CREATE TABLE notification_templates (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key             text NOT NULL,
    channel         text NOT NULL,      -- in_app|email|push|dashboard
    subject         text,
    body            text NOT NULL,      -- supports {{placeholders}}
    UNIQUE (organization_id, key, channel)
);
CREATE TABLE notifications (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    recipient_user_id uuid REFERENCES users(id),
    channel         text NOT NULL,
    title           text, body text NOT NULL,
    read_at         timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE report_schedules (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    report_type     text NOT NULL,      -- attendance|productivity|application|website|screenshot|shift
    cron            text NOT NULL,
    format          text NOT NULL DEFAULT 'pdf', -- csv|xlsx|pdf
    filters         jsonb NOT NULL DEFAULT '{}',
    recipients      jsonb NOT NULL DEFAULT '[]',
    enabled         boolean NOT NULL DEFAULT true
);

CREATE TABLE webhooks (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    url             text NOT NULL,
    secret          text NOT NULL,      -- HMAC signing
    events          jsonb NOT NULL,     -- ["shift.started", ...]
    enabled         boolean NOT NULL DEFAULT true
);
CREATE TABLE webhook_deliveries (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    webhook_id      uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event           text NOT NULL, payload jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'pending',
    attempts        int NOT NULL DEFAULT 0,
    last_attempt_at timestamptz
);

CREATE TABLE ai_jobs (
    id              uuid PRIMARY KEY DEFAULT uuidv7(),
    organization_id uuid NOT NULL,
    kind            text NOT NULL,      -- summary|anomaly|nl_query
    scope           jsonb NOT NULL,     -- RBAC scope snapshot
    status          text NOT NULL DEFAULT 'queued',
    result          jsonb,
    requested_by    uuid REFERENCES users(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

## 11. Audit log (append-only, partitioned)

```sql
CREATE TABLE audit_logs (
    id              uuid DEFAULT uuidv7(),
    organization_id uuid,               -- null for platform-level actions
    actor_user_id   uuid,
    action          text NOT NULL,
    target_type     text, target_id uuid,
    ip              inet,
    device_id       uuid,
    old_value       jsonb,
    new_value       jsonb,
    reason          text,
    at              timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, at)
) PARTITION BY RANGE (at);
CREATE INDEX ix_audit_org_at ON audit_logs(organization_id, at);
-- No UPDATE/DELETE granted to app role; append-only via INSERT only.
```

---

## 12. Row-Level Security (tenant isolation)

Applied to every tenant-owned table:

```sql
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON employees
    USING (organization_id = current_setting('app.current_org')::uuid);
-- The API sets:  SET LOCAL app.current_org = '<org uuid>';  per request/transaction.
-- Repeat for all tenant tables. Platform-level tables (permissions) are exempt.
```

---

## 13. Partitioning & retention (spec 58, 82)

- Monthly range partitions on `application_events`, `website_events`, `activity_intervals`,
  `screenshots`, `audit_logs`. Beat job pre-creates next month's partitions and detaches/archives old ones.
- Retention configured per data class in `organizations.settings.retention` (never hard-coded):
  `{shift, attendance, application, website, screenshots, audit, ai}` each with a day count.
- A daily retention worker deletes expired rows/objects and writes audit records for deletions.

## 14. Rollups (read performance, spec 58/C2)

Aggregation tables refreshed by workers, read by dashboards/reports:

```sql
CREATE TABLE daily_employee_rollup (
    organization_id uuid NOT NULL, employee_id uuid NOT NULL, work_date date NOT NULL,
    tracked_seconds int, productive_seconds int, neutral_seconds int,
    unproductive_seconds int, idle_seconds int, worked_seconds int,
    productivity_indicator numeric(5,2),
    PRIMARY KEY (organization_id, employee_id, work_date)
);
-- plus daily_team_rollup, daily_department_rollup with the same measures.
```

Every measure here is derived from authoritative shift/event data (spec 54).
