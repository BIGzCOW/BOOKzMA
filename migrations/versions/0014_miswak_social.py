"""Add opt-in miswak challenges, league preference, and buddy links.

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "miswak_profiles",
        sa.Column("league_opt_in", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_table(
        "miswak_challenges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("duration IN (7, 30)", name="ck_miswak_challenge_duration"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_miswak_challenge_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_miswak_challenge_active_user",
        "miswak_challenges",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "miswak_buddy_invites",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("inviter_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(
        "ix_miswak_buddy_invites_inviter", "miswak_buddy_invites", ["inviter_id"]
    )
    op.create_table(
        "miswak_buddy_pairs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_a", sa.BigInteger(), nullable=False),
        sa.Column("user_b", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_nudge_on", sa.Date(), nullable=True),
        sa.CheckConstraint("user_a < user_b", name="ck_miswak_buddy_pair_order"),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_miswak_buddy_pair_status"),
        sa.ForeignKeyConstraint(["user_a"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_b"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_miswak_buddy_pair_active",
        "miswak_buddy_pairs",
        ["user_a", "user_b"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_miswak_buddy_pair_active", table_name="miswak_buddy_pairs")
    op.drop_table("miswak_buddy_pairs")
    op.drop_index("ix_miswak_buddy_invites_inviter", table_name="miswak_buddy_invites")
    op.drop_table("miswak_buddy_invites")
    op.drop_index("uq_miswak_challenge_active_user", table_name="miswak_challenges")
    op.drop_table("miswak_challenges")
    op.drop_column("miswak_profiles", "league_opt_in")