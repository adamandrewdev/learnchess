"""games can be excluded from playstyle statistics (PLAN D31)

Revision ID: c4e8a1b5d602
Revises: b7d2f4a8c911
Create Date: 2026-11-06 21:45:00
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e8a1b5d602"
down_revision = "b7d2f4a8c911"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("exclude_from_profile", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("games", "exclude_from_profile")
