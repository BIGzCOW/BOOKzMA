"""Persist expiring one-time study-buddy invitations.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buddy_invites",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("inviter_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_buddy_invites_inviter_id", "buddy_invites", ["inviter_id"])


def downgrade() -> None:
    op.drop_index("ix_buddy_invites_inviter_id", table_name="buddy_invites")
    op.drop_table("buddy_invites")