"""Add durable text broadcast campaigns and per-user delivery state.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broadcast_campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.String(length=4096), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'completed', 'cancelled')",
            name="ck_broadcast_campaign_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "broadcast_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(length=128), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
            name="ck_broadcast_delivery_status",
        ),
        sa.ForeignKeyConstraint(["campaign_id"], ["broadcast_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", "user_id", name="uq_broadcast_delivery_campaign_user"),
    )
    op.create_index(
        "ix_broadcast_delivery_campaign_status",
        "broadcast_deliveries",
        ["campaign_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_broadcast_delivery_campaign_status", table_name="broadcast_deliveries")
    op.drop_table("broadcast_deliveries")
    op.drop_table("broadcast_campaigns")
