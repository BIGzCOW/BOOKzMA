"""Add anonymous Mesbak buddy matching.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mesbak_buddy_pairs",
        sa.Column("pair_type", sa.String(length=16), server_default="invite", nullable=False),
    )
    op.create_check_constraint(
        "ck_mesbak_buddy_pair_type",
        "mesbak_buddy_pairs",
        "pair_type IN ('invite', 'random')",
    )
    op.create_table(
        "mesbak_buddy_queue",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["mesbak_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_mesbak_buddy_queue_joined",
        "mesbak_buddy_queue",
        ["joined_at", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mesbak_buddy_queue_joined", table_name="mesbak_buddy_queue")
    op.drop_table("mesbak_buddy_queue")
    op.drop_constraint("ck_mesbak_buddy_pair_type", "mesbak_buddy_pairs", type_="check")
    op.drop_column("mesbak_buddy_pairs", "pair_type")
