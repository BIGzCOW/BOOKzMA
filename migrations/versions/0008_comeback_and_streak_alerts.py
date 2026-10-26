"""Comeback-streak state on users and daily dedup for streak-at-risk alerts.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("broken_streak_days", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("comeback_bonus_days", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("comeback_base_day", sa.Date(), nullable=True))
    op.create_table(
        "streak_alerts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_index("ix_streak_alerts_day", "streak_alerts", ["day"])


def downgrade() -> None:
    op.drop_index("ix_streak_alerts_day", table_name="streak_alerts")
    op.drop_table("streak_alerts")
    op.drop_column("users", "comeback_base_day")
    op.drop_column("users", "comeback_bonus_days")
    op.drop_column("users", "broken_streak_days")
