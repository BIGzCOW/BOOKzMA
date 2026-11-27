"""Track first bot starts, daily activity, and leaderboard preference.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_reading_logs_day", "reading_logs", ["day"])
    op.add_column(
        "users",
        sa.Column("leaderboard_opt_out", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("display_name", sa.String(length=128), nullable=True))
    op.add_column(
        "users",
        sa.Column("broadcast_unavailable", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("users", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "activity_days",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_index("ix_activity_days_day", "activity_days", ["day"])


def downgrade() -> None:
    op.drop_index("ix_activity_days_day", table_name="activity_days")
    op.drop_index("ix_reading_logs_day", table_name="reading_logs")
    op.drop_table("activity_days")
    op.drop_column("users", "started_at")
    op.drop_column("users", "display_name")
    op.drop_column("users", "broadcast_unavailable")
    op.drop_column("users", "leaderboard_opt_out")
