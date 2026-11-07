"""eval after each player move, the baseline for the next blunder warning (PLAN D27)

Revision ID: b7d2f4a8c911
Revises: a3c1e9d27f30
Create Date: 2026-11-06 15:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2f4a8c911"
down_revision = "a3c1e9d27f30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moves", sa.Column("eval_cp_after", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("moves", "eval_cp_after")
