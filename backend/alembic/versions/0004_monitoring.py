"""phase 4: monitoring event tables (application/website/activity/screenshots) + RLS

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14

Production note: on PostgreSQL these high-volume tables should be converted to
PARTITION BY RANGE (occurred_at) with monthly partitions and a composite PK (id, occurred_at).
This migration creates them as regular tables for portability; a follow-up ops migration (or a
managed-partitioning extension like pg_partman) introduces partitions without changing the
query surface. RLS is applied here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "application_events",
    "website_events",
    "activity_intervals",
    "screenshots",
    "screenshot_access_log",
]


def _org():
    return sa.Column(
        "organization_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "application_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("application", sa.String(255), nullable=False),
        sa.Column("process_name", sa.String(255), nullable=True),
        sa.Column("window_title", sa.String(512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_appevent_key"),
    )
    op.create_index("ix_application_events_organization_id", "application_events", ["organization_id"])
    op.create_index("ix_appev_emp", "application_events", ["organization_id", "employee_id", "occurred_at"])

    op.create_table(
        "website_events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_webevent_key"),
    )
    op.create_index("ix_website_events_organization_id", "website_events", ["organization_id"])
    op.create_index("ix_webev_emp", "website_events", ["organization_id", "employee_id", "occurred_at"])

    op.create_table(
        "activity_intervals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("keyboard_pct", sa.SmallInteger, nullable=True),
        sa.Column("mouse_pct", sa.SmallInteger, nullable=True),
        sa.Column("combined_pct", sa.SmallInteger, nullable=True),
        sa.Column("is_idle", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_actint_key"),
    )
    op.create_index("ix_activity_intervals_organization_id", "activity_intervals", ["organization_id"])
    op.create_index("ix_actint_emp", "activity_intervals", ["organization_id", "employee_id", "occurred_at"])

    op.create_table(
        "screenshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("shift_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("thumb_key", sa.String(512), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("bytes", sa.Integer, nullable=True),
        sa.Column("watermarked", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("encryption_key_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.UniqueConstraint("organization_id", "event_key", name="uq_screenshot_key"),
    )
    op.create_index("ix_screenshots_organization_id", "screenshots", ["organization_id"])
    op.create_index("ix_shots_emp", "screenshots", ["organization_id", "employee_id", "occurred_at"])

    op.create_table(
        "screenshot_access_log",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("screenshot_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_screenshot_access_log_organization_id", "screenshot_access_log", ["organization_id"])

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
