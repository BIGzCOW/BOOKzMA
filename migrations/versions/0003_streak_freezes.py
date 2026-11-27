"""Track earned and used streak freezes separately from reading logs.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "streak_freezes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.CheckConstraint("kind IN ('earned', 'used')", name="ck_streak_freeze_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "day", name="uq_streak_freeze_user_kind_day"),
    )


def downgrade() -> None:
    op.drop_table("streak_freezes")
