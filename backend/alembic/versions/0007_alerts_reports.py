"""phase 7: alerts, notifications, report schedules, webhooks + RLS

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "alert_rules",
    "alerts",
    "notification_templates",
    "notifications",
    "report_schedules",
    "webhooks",
    "webhook_deliveries",
]


def _org():
    return sa.Column(
        "organization_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("key", sa.String(48), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="organization"),
        sa.Column("scope_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("params", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("channels", pg.JSONB, nullable=False, server_default="[]"),
    )
    op.create_index("ix_alert_rules_organization_id", "alert_rules", ["organization_id"])

    op.create_table(
        "alerts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("rule_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("employee_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.String(512), nullable=False),
        sa.Column("context", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("dedup_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "dedup_key", name="uq_alert_dedup"),
    )
    op.create_index("ix_alerts_organization_id", "alerts", ["organization_id"])
    op.create_index("ix_alerts_org_created", "alerts", ["organization_id", "created_at"])

    op.create_table(
        "notification_templates",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.UniqueConstraint("organization_id", "key", "channel", name="uq_notif_template"),
    )
    op.create_index("ix_notification_templates_organization_id", "notification_templates", ["organization_id"])

    op.create_table(
        "notifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("recipient_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])

    op.create_table(
        "report_schedules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column("format", sa.String(8), nullable=False, server_default="pdf"),
        sa.Column("filters", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("recipients", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_report_schedules_organization_id", "report_schedules", ["organization_id"])

    op.create_table(
        "webhooks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("events", pg.JSONB, nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_webhooks_organization_id", "webhooks", ["organization_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("webhook_id", pg.UUID(as_uuid=True), sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(48), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_deliveries_organization_id", "webhook_deliveries", ["organization_id"])
    op.create_index("ix_wh_delivery_org", "webhook_deliveries", ["organization_id", "status"])

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
