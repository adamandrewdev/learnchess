"""end-of-game review summaries (PLAN D28)

Revision ID: d5f9b2c6e713
Revises: c4e8a1b5d602
Create Date: 2026-11-06 22:30:00
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f9b2c6e713"
down_revision = "c4e8a1b5d602"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "game_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_game_reviews_game_id"), "game_reviews", ["game_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_game_reviews_game_id"), table_name="game_reviews")
    op.drop_table("game_reviews")
