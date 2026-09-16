"""phase 6: projects, tasks, task time entries, timesheets, corrections + RLS

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "projects",
    "tasks",
    "task_time_entries",
    "timesheets",
    "timesheet_entries",
    "timesheet_corrections",
]


def _org():
    return sa.Column(
        "organization_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])

    op.create_table(
        "tasks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("project_id", pg.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"])

    op.create_table(
        "task_time_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("task_id", pg.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), sa.ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="agent"),
    )
    op.create_index("ix_task_time_entries_organization_id", "task_time_entries", ["organization_id"])
    op.create_index("ix_tte_emp", "task_time_entries", ["organization_id", "employee_id", "started_at"])

    op.create_table(
        "timesheets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("approved_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "employee_id", "period_start", "period_end", name="uq_timesheet_period"),
    )
    op.create_index("ix_timesheets_organization_id", "timesheets", ["organization_id"])

    op.create_table(
        "timesheet_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("timesheet_id", pg.UUID(as_uuid=True), sa.ForeignKey("timesheets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("scheduled_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("worked_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("break_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overtime_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(24), nullable=True),
    )
    op.create_index("ix_timesheet_entries_organization_id", "timesheet_entries", ["organization_id"])

    op.create_table(
        "timesheet_corrections",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("timesheet_id", pg.UUID(as_uuid=True), sa.ForeignKey("timesheets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entry_id", pg.UUID(as_uuid=True), sa.ForeignKey("timesheet_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_type", sa.String(32), nullable=False),
        sa.Column("old_value", pg.JSONB, nullable=True),
        sa.Column("new_value", pg.JSONB, nullable=True),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_timesheet_corrections_organization_id", "timesheet_corrections", ["organization_id"])

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
    for table in reversed(RLS_TABLES):
        op.drop_table(table)
