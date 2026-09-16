"""RBAC constants: permission keys and default role grants.

This is the single source of truth for the seed. It mirrors docs/07-rbac-and-policy-model.md.
Grants marked scoped ("team"/"self") are enforced at query time by narrowing to the caller's
scope; the permission itself is still granted here.
"""
from __future__ import annotations

# --- Permission keys ---
PERMISSIONS: dict[str, str] = {
    # directory
    "employee.view": "View employees",
    "employee.manage": "Create/update/delete employees",
    "department.manage": "Manage departments",
    "team.manage": "Manage teams",
    "user.manage": "Manage users",
    "role.manage": "Manage roles and permissions",
    # devices
    "device.view": "View devices",
    "device.approve": "Approve devices",
    "device.revoke": "Revoke devices",
    # scheduling / policy
    "schedule.view": "View schedules",
    "schedule.manage": "Manage schedules",
    "shiftpolicy.manage": "Manage shift policies",
    "monitoringpolicy.manage": "Manage monitoring policies",
    "leave.view": "View leave",
    "leave.approve": "Approve leave",
    "holiday.manage": "Manage holidays",
    # shifts / attendance
    "shift.view": "View shifts",
    "shift.start_own": "Start own shift",
    "shift.control_own": "Pause/resume/end own shift",
    "shift.force_stop": "Force-stop a shift",
    "attendance.view": "View attendance",
    # monitoring data
    "activity.view": "View activity",
    "application.view": "View application usage",
    "website.view": "View website usage",
    "screenshot.view": "View screenshots",
    "screenshot.download": "Download screenshots",
    # productivity
    "classification.manage": "Manage classifications",
    "productivity.manage": "Manage productivity categories/formula",
    # projects / timesheets
    "project.view": "View projects",
    "project.manage": "Manage projects",
    "task.time_track": "Track time on tasks",
    "timesheet.view": "View timesheets",
    "timesheet.approve": "Approve timesheets",
    "timesheet.edit": "Edit timesheets",
    "correction.review": "Review corrections",
    "rate.view": "View pay rates",
    "rate.manage": "Manage pay rates",
    "payroll.run": "Run payroll and view payroll data",
    # alerts / reports / analytics
    "alert.view": "View alerts",
    "alert.manage": "Manage alert rules",
    "report.view": "View reports",
    "report.manage": "Manage/schedule reports",
    "analytics.view": "View analytics",
    "analytics.org": "View org-wide analytics",
    # ai / audit / settings / integrations
    "ai.use": "Use AI features",
    "audit.view": "View audit logs",
    "settings.manage": "Manage settings",
    "integration.manage": "Manage integrations",
    "webhook.manage": "Manage webhooks",
    # platform
    "org.manage": "Manage organization",
    "platform.admin": "Platform administration",
}

# System role keys
SUPER_ADMIN = "super_admin"
ORG_ADMIN = "org_admin"
HR = "hr"
MANAGER = "manager"
SUPERVISOR = "supervisor"
EMPLOYEE = "employee"

SYSTEM_ROLES: dict[str, str] = {
    SUPER_ADMIN: "Super Admin",
    ORG_ADMIN: "Organization Admin",
    HR: "HR / Admin",
    MANAGER: "Manager",
    SUPERVISOR: "Supervisor",
    EMPLOYEE: "Employee",
}

# Default grants per role (super_admin implicitly gets everything).
ROLE_GRANTS: dict[str, list[str]] = {
    SUPER_ADMIN: list(PERMISSIONS.keys()),
    ORG_ADMIN: [
        k for k in PERMISSIONS
        if k not in {"platform.admin"}
    ],
    HR: [
        "employee.view", "employee.manage", "department.manage", "team.manage",
        "device.view", "device.approve", "device.revoke",
        "schedule.view", "schedule.manage", "leave.view", "leave.approve", "holiday.manage",
        "shift.view", "shift.force_stop", "attendance.view",
        "activity.view", "application.view", "website.view", "screenshot.view",
        "project.view", "project.manage",
        "timesheet.view", "timesheet.approve", "timesheet.edit", "correction.review",
        "alert.view", "alert.manage", "report.view", "report.manage",
        "analytics.view", "analytics.org", "ai.use", "audit.view",
        "rate.view", "payroll.run",
    ],
    MANAGER: [
        "employee.view", "device.view", "schedule.view", "schedule.manage",
        "leave.view", "leave.approve", "shift.view", "shift.force_stop", "attendance.view",
        "activity.view", "application.view", "website.view", "screenshot.view",
        "screenshot.download", "project.view", "project.manage", "task.time_track",
        "timesheet.view", "timesheet.approve", "timesheet.edit", "correction.review",
        "alert.view", "alert.manage", "report.view", "analytics.view", "ai.use",
    ],
    SUPERVISOR: [
        "employee.view", "device.view", "schedule.view", "leave.view",
        "shift.view", "attendance.view", "activity.view", "application.view",
        "website.view", "task.time_track", "timesheet.view",
        "alert.view", "report.view", "analytics.view", "ai.use",
    ],
    EMPLOYEE: [
        "employee.view", "device.view", "schedule.view", "leave.view",
        "shift.view", "shift.start_own", "shift.control_own", "attendance.view",
        "activity.view", "application.view", "website.view",
        "project.view", "task.time_track", "timesheet.view",
        "report.view", "analytics.view",
    ],
}
