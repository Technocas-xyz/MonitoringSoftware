"""phase 2: scheduling, policies, shifts, breaks, attendance, leave, holidays + RLS

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "work_schedules",
    "schedule_assignments",
    "holiday_calendars",
    "holiday_days",
    "leave_requests",
    "shift_policies",
    "monitoring_policies",
    "policy_assignments",
    "shifts",
    "shift_events",
    "breaks",
    "attendance",
]


def _org_fk(nullable=False):
    return sa.Column(
        "organization_id",
        pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "work_schedules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("definition", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_work_schedules_organization_id", "work_schedules", ["organization_id"])

    op.create_table(
        "schedule_assignments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("schedule_id", pg.UUID(as_uuid=True), sa.ForeignKey("work_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_schedule_assignments_organization_id", "schedule_assignments", ["organization_id"])
    op.create_index("ix_sched_assign_target", "schedule_assignments", ["organization_id", "target_type", "target_id"])

    op.create_table(
        "holiday_calendars",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
    )
    op.create_index("ix_holiday_calendars_organization_id", "holiday_calendars", ["organization_id"])

    op.create_table(
        "holiday_days",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("calendar_id", pg.UUID(as_uuid=True), sa.ForeignKey("holiday_calendars.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
    )
    op.create_index("ix_holiday_days_organization_id", "holiday_days", ["organization_id"])
    op.create_index("ix_holiday_cal_day", "holiday_days", ["calendar_id", "day"], unique=True)

    op.create_table(
        "leave_requests",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(512), nullable=True),
        sa.Column("approver_user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_leave_requests_organization_id", "leave_requests", ["organization_id"])
    op.create_index("ix_leave_emp", "leave_requests", ["organization_id", "employee_id", "start_date"])

    op.create_table(
        "shift_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("tracking_mode", sa.String(32), nullable=False, server_default="hybrid"),
        sa.Column("earliest_clock_in_min", sa.Integer, nullable=True),
        sa.Column("latest_clock_in_min", sa.Integer, nullable=True),
        sa.Column("late_threshold_min", sa.Integer, nullable=False, server_default="15"),
        sa.Column("allow_break", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("max_break_seconds", sa.Integer, nullable=True),
        sa.Column("allow_multiple_breaks", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("allow_early_clockout", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("allow_overtime", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("overtime_requires_approval", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("auto_start", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("auto_end", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("monitoring_required", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shift_policies_organization_id", "shift_policies", ["organization_id"])

    op.create_table(
        "monitoring_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("monitor_applications", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("monitor_websites", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("website_mode", sa.String(16), nullable=False, server_default="domain"),
        sa.Column("monitor_idle", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("idle_threshold_seconds", sa.Integer, nullable=False, server_default="600"),
        sa.Column("idle_classification", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("monitor_kbd_mouse", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("screenshot_mode", sa.String(16), nullable=False, server_default="off"),
        sa.Column("screenshot_interval_seconds", sa.Integer, nullable=True),
        sa.Column("screenshot_capture_scope", sa.String(16), nullable=False, server_default="working_only"),
        sa.Column("screenshot_watermark", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_monitoring_policies_organization_id", "monitoring_policies", ["organization_id"])

    op.create_table(
        "policy_assignments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("policy_kind", sa.String(16), nullable=False),
        sa.Column("policy_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("allow_override", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_policy_assignments_organization_id", "policy_assignments", ["organization_id"])
    op.create_index("ix_policy_assign", "policy_assignments", ["organization_id", "policy_kind", "target_type", "target_id"])

    op.create_table(
        "shifts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_id", pg.UUID(as_uuid=True), sa.ForeignKey("work_schedules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("policy_snapshot", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("schedule_snapshot", pg.JSONB, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shifts_organization_id", "shifts", ["organization_id"])
    op.create_index("ix_shifts_emp_start", "shifts", ["organization_id", "employee_id", "scheduled_start"])
    # One active shift per employee (spec 5 / edge case 8)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_shift_per_employee
        ON shifts (organization_id, employee_id)
        WHERE state IN ('AVAILABLE','WORKING','ON_BREAK','PAUSED')
        """
    )

    op.create_table(
        "shift_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("shift_id", pg.UUID(as_uuid=True), sa.ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_shift_event_key"),
    )
    op.create_index("ix_shift_events_organization_id", "shift_events", ["organization_id"])
    op.create_index("ix_shift_events_shift", "shift_events", ["shift_id", "occurred_at"])

    op.create_table(
        "breaks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("shift_id", pg.UUID(as_uuid=True), sa.ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_seconds", sa.Integer, nullable=True),
        sa.Column("paid", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("exceeded", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("approved_by", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_breaks_organization_id", "breaks", ["organization_id"])
    op.create_index("ix_breaks_shift", "breaks", ["shift_id"])

    op.create_table(
        "attendance",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org_fk(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), sa.ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worked_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("break_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idle_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("late_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("early_leave_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overtime_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "employee_id", "work_date", name="uq_attendance_day"),
    )
    op.create_index("ix_attendance_organization_id", "attendance", ["organization_id"])
    op.create_index("ix_attendance_org_date", "attendance", ["organization_id", "work_date"])

    # RLS on all new tenant tables
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (organization_id = current_setting('app.current_org', true)::uuid)
            WITH CHECK (organization_id = current_setting('app.current_org', true)::uuid)
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS uq_active_shift_per_employee")
    for table in reversed(RLS_TABLES):
        op.drop_table(table)
