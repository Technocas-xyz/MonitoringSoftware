"""phase 5: productivity categories, classifications, daily rollups + RLS

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RLS_TABLES = [
    "productivity_categories",
    "application_classifications",
    "website_classifications",
    "daily_employee_rollup",
    "daily_team_rollup",
    "daily_department_rollup",
]


def _org():
    return sa.Column(
        "organization_id", pg.UUID(as_uuid=True),
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )


def _measures():
    return [
        sa.Column("tracked_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("productive_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("neutral_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unproductive_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("idle_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("productivity_indicator", sa.Numeric(5, 2), nullable=False, server_default="0"),
    ]


def upgrade() -> None:
    op.create_table(
        "productivity_categories",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("weight", sa.Numeric(4, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("organization_id", "key", name="uq_prod_cat_key"),
    )
    op.create_index("ix_productivity_categories_organization_id", "productivity_categories", ["organization_id"])

    op.create_table(
        "application_classifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("application", sa.String(255), nullable=False),
        sa.Column("category_id", pg.UUID(as_uuid=True), sa.ForeignKey("productivity_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="organization"),
        sa.Column("scope_id", pg.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("organization_id", "application", "scope_type", "scope_id", name="uq_appclass"),
    )
    op.create_index("ix_application_classifications_organization_id", "application_classifications", ["organization_id"])
    op.create_index("ix_appclass_org_app", "application_classifications", ["organization_id", "application"])

    op.create_table(
        "website_classifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        _org(),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("category_id", pg.UUID(as_uuid=True), sa.ForeignKey("productivity_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="organization"),
        sa.Column("scope_id", pg.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("organization_id", "domain", "scope_type", "scope_id", name="uq_webclass"),
    )
    op.create_index("ix_website_classifications_organization_id", "website_classifications", ["organization_id"])
    op.create_index("ix_webclass_org_domain", "website_classifications", ["organization_id", "domain"])

    op.create_table(
        "daily_employee_rollup",
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("employee_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_date", sa.Date, primary_key=True),
        sa.Column("worked_seconds", sa.Integer, nullable=False, server_default="0"),
        *_measures(),
    )

    op.create_table(
        "daily_team_rollup",
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("team_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_date", sa.Date, primary_key=True),
        sa.Column("employees", sa.Integer, nullable=False, server_default="0"),
        *_measures(),
    )

    op.create_table(
        "daily_department_rollup",
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("work_date", sa.Date, primary_key=True),
        sa.Column("employees", sa.Integer, nullable=False, server_default="0"),
        *_measures(),
    )

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
