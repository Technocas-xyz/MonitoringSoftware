"""SQLAlchemy models. Import all here so Alembic autogenerate and metadata see them."""
from app.models.audit import AuditLog
from app.models.devices import Device
from app.models.directory import Department, Employee, Team
from app.models.identity import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.models.organization import Organization
from app.models.policy import MonitoringPolicy, PolicyAssignment, ShiftPolicy
from app.models.scheduling import (
    HolidayCalendar,
    HolidayDay,
    LeaveRequest,
    ScheduleAssignment,
    WorkSchedule,
)
from app.models.monitoring import (
    ActivityInterval,
    ApplicationEvent,
    Screenshot,
    ScreenshotAccessLog,
    WebsiteEvent,
)
from app.models.productivity import (
    ApplicationClassification,
    DailyDepartmentRollup,
    DailyEmployeeRollup,
    DailyTeamRollup,
    ProductivityCategory,
    WebsiteClassification,
)
from app.models.ai import AIJob
from app.models.geo import GeofenceEvent, OfficeLocation
from app.models.payroll import PayrollLine, PayrollRun
from app.models.alerts import (
    Alert,
    AlertRule,
    Notification,
    NotificationTemplate,
    ReportSchedule,
    Webhook,
    WebhookDelivery,
)
from app.models.projects import (
    Project,
    Task,
    TaskTimeEntry,
    Timesheet,
    TimesheetCorrection,
    TimesheetEntry,
)
from app.models.shifts import Attendance, Break, Shift, ShiftEvent

__all__ = [
    "Organization",
    "User",
    "Role",
    "Permission",
    "RolePermission",
    "UserRole",
    "Department",
    "Team",
    "Employee",
    "Device",
    "AuditLog",
    "WorkSchedule",
    "ScheduleAssignment",
    "HolidayCalendar",
    "HolidayDay",
    "LeaveRequest",
    "ShiftPolicy",
    "MonitoringPolicy",
    "PolicyAssignment",
    "Shift",
    "ShiftEvent",
    "Break",
    "Attendance",
    "ApplicationEvent",
    "WebsiteEvent",
    "ActivityInterval",
    "Screenshot",
    "ScreenshotAccessLog",
    "ProductivityCategory",
    "ApplicationClassification",
    "WebsiteClassification",
    "DailyEmployeeRollup",
    "DailyTeamRollup",
    "DailyDepartmentRollup",
    "Project",
    "Task",
    "TaskTimeEntry",
    "Timesheet",
    "TimesheetEntry",
    "TimesheetCorrection",
    "AlertRule",
    "Alert",
    "NotificationTemplate",
    "Notification",
    "ReportSchedule",
    "Webhook",
    "WebhookDelivery",
    "AIJob",
    "OfficeLocation",
    "GeofenceEvent",
    "PayrollRun",
    "PayrollLine",
]
