// Shapes mirror the backend response models (backend/app/**/schemas + routers).

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Me {
  user_id: string;
  organization_id: string;
  email: string;
  permissions: string[];
  roles: string[];
}

export interface Overview {
  employees: number;
  working: number;
  on_break: number;
  not_started: number;
  average_worked_seconds: number;
  productivity_indicator: number;
}

export interface Employee {
  id: string;
  full_name: string;
  employee_code: string | null;
  department_id: string | null;
  team_id: string | null;
  timezone: string | null;
  status: string;
  hired_at: string | null;
  terminated_at: string | null;
  hourly_rate: number | null;
}

export interface EmployeeDetail {
  employee_id: string;
  work_date: string;
  attendance: {
    status: string | null;
    worked_seconds: number;
    break_seconds: number;
    idle_seconds: number;
    late_seconds: number;
    overtime_seconds: number;
  };
  productivity: {
    tracked_seconds: number;
    productive_seconds: number;
    neutral_seconds: number;
    unproductive_seconds: number;
    indicator: number;
  };
}

export interface TimelineEntry {
  at: string;
  kind: "shift" | "application" | "website";
  label: string;
  detail: string | null;
}

export interface AttendanceRow {
  id: string;
  employee_id: string;
  shift_id: string | null;
  work_date: string;
  status: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  worked_seconds: number;
  break_seconds: number;
  idle_seconds: number;
  late_seconds: number;
  early_leave_seconds: number;
  overtime_seconds: number;
}

export interface Shift {
  id: string;
  employee_id: string;
  state: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  timezone: string;
  version: number;
}

export interface AlertRow {
  id: string;
  rule_id: string | null;
  employee_id: string | null;
  severity: string;
  message: string;
  status: string;
  created_at: string;
}

export interface Device {
  id: string;
  employee_id: string;
  hostname: string | null;
  os: string | null;
  agent_version: string | null;
  status: string; // pending | approved | revoked
  last_seen_at: string | null;
  approved_at: string | null;
  revoked_at: string | null;
}

export interface DeviceApproved extends Device {
  signing_secret: string | null; // returned once, on approval
}
