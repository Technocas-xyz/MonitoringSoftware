"""phase 8: ai_jobs + RLS

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("scope", pg.JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("result", pg.JSONB, nullable=True),
        sa.Column("requested_by", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_jobs_organization_id", "ai_jobs", ["organization_id"])

    op.execute("ALTER TABLE ai_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON ai_jobs
        USING (organization_id = current_setting('app.current_org', true)::uuid)
        WITH CHECK (organization_id = current_setting('app.current_org', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_jobs")
    op.execute("ALTER TABLE ai_jobs DISABLE ROW LEVEL SECURITY")
    op.drop_table("ai_jobs")
