"""phase 9: geofencing + payroll + RLS

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = ["office_locations", "geofence_events", "payroll_runs", "payroll_lines"]


def _org():
    return sa.Column(
        "organization_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "office_locations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("radius_meters", sa.Integer, nullable=False, server_default="150"),
    )
    op.create_index("ix_office_locations_organization_id", "office_locations", ["organization_id"])

    op.create_table(
        "geofence_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("inside", sa.Boolean, nullable=False),
        sa.Column("distance_meters", sa.Float, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_geofence_events_organization_id", "geofence_events", ["organization_id"])
    op.create_index("ix_geofence_emp", "geofence_events", ["organization_id", "employee_id", "occurred_at"])

    op.create_table(
        "payroll_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("rules_snapshot", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payroll_runs_organization_id", "payroll_runs", ["organization_id"])

    op.create_table(
        "payroll_lines",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("run_id", pg.UUID(as_uuid=True), sa.ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("line_type", sa.String(16), nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("rate", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_payroll_lines_organization_id", "payroll_lines", ["organization_id"])
    op.create_index("ix_payroll_line_run", "payroll_lines", ["organization_id", "run_id"])

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
