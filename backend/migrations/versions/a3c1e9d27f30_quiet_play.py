"""quiet play: think time and blunder warning per move (PLAN D27, D30)

Revision ID: a3c1e9d27f30
Revises: 54d885a60640
Create Date: 2026-11-06 12:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "a3c1e9d27f30"
down_revision = "54d885a60640"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moves", sa.Column("think_ms", sa.Integer(), nullable=True))
    op.add_column("moves", sa.Column("warning", sa.String(length=120), nullable=True))
    op.add_column("moves", sa.Column("warning_outcome", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("moves", "warning_outcome")
    op.drop_column("moves", "warning")
    op.drop_column("moves", "think_ms")
