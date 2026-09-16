"""phase 3: device signing secret + tracking state for the desktop agent

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("signing_secret", sa.String(128), nullable=True))
    op.add_column("devices", sa.Column("tracking_state", sa.String(24), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "tracking_state")
    op.drop_column("devices", "signing_secret")
