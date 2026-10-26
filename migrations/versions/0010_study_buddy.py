"""Study-buddy queue and pairs (C-06).

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buddy_queue",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "buddy_pairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_a", sa.BigInteger(), nullable=False),
        sa.Column("user_b", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.BigInteger(), nullable=True),
        sa.Column("last_nudge_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["user_a"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_b"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_buddy_pair_status"),
        sa.CheckConstraint("user_a <> user_b", name="ck_buddy_pair_distinct"),
    )
    op.create_index(
        "uq_buddy_pair_user_a_active",
        "buddy_pairs",
        ["user_a"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_buddy_pair_user_b_active",
        "buddy_pairs",
        ["user_b"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_buddy_pair_user_b_active", table_name="buddy_pairs")
    op.drop_index("uq_buddy_pair_user_a_active", table_name="buddy_pairs")
    op.drop_table("buddy_pairs")
    op.drop_table("buddy_queue")
