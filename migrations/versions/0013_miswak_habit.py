"""Add the optional miswak habit and targeted campaign fields.

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "broadcast_campaigns",
        sa.Column("audience", sa.String(length=16), server_default="all", nullable=False),
    )
    op.add_column("broadcast_campaigns", sa.Column("media_type", sa.String(length=8)))
    op.add_column("broadcast_campaigns", sa.Column("media_file_id", sa.String(length=512)))
    op.add_column("broadcast_campaigns", sa.Column("button_label", sa.String(length=64)))
    op.add_column("broadcast_campaigns", sa.Column("button_url", sa.String(length=2048)))
    op.create_check_constraint(
        "ck_broadcast_campaign_audience",
        "broadcast_campaigns",
        "audience IN ('all', 'miswak')",
    )
    op.create_check_constraint(
        "ck_broadcast_campaign_media_type",
        "broadcast_campaigns",
        "media_type IS NULL OR media_type IN ('photo', 'video')",
    )

    op.create_table(
        "miswak_profiles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("daily_goal", sa.Integer(), server_default="1", nullable=False),
        sa.Column("next_daily_goal", sa.Integer(), nullable=True),
        sa.Column("goal_effective_on", sa.Date(), nullable=True),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("daily_goal BETWEEN 1 AND 5", name="ck_miswak_profile_daily_goal"),
        sa.CheckConstraint(
            "next_daily_goal IS NULL OR next_daily_goal BETWEEN 1 AND 5",
            name="ck_miswak_profile_next_goal",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "miswak_entries",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("daily_goal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("slot BETWEEN 1 AND 5", name="ck_miswak_entry_slot"),
        sa.CheckConstraint("daily_goal BETWEEN 1 AND 5", name="ck_miswak_entry_goal"),
        sa.CheckConstraint("slot <= daily_goal", name="ck_miswak_entry_slot_goal"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "day", "slot"),
    )
    op.create_index("ix_miswak_entries_day", "miswak_entries", ["day"])
    op.create_table(
        "miswak_reminders",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("remind_at", sa.Time(), nullable=False),
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.Column("attempt_date", sa.Date(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retry_after_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("slot BETWEEN 1 AND 5", name="ck_miswak_reminder_slot"),
        sa.ForeignKeyConstraint(["user_id"], ["miswak_profiles.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "slot"),
        sa.UniqueConstraint("user_id", "remind_at", name="uq_miswak_reminder_user_time"),
    )
    op.create_table(
        "miswak_badges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("awarded_day", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code", name="uq_miswak_badge_user_code"),
    )


def downgrade() -> None:
    op.drop_table("miswak_badges")
    op.drop_table("miswak_reminders")
    op.drop_index("ix_miswak_entries_day", table_name="miswak_entries")
    op.drop_table("miswak_entries")
    op.drop_table("miswak_profiles")
    op.drop_constraint(
        "ck_broadcast_campaign_media_type", "broadcast_campaigns", type_="check"
    )
    op.drop_constraint("ck_broadcast_campaign_audience", "broadcast_campaigns", type_="check")
    op.drop_column("broadcast_campaigns", "button_url")
    op.drop_column("broadcast_campaigns", "button_label")
    op.drop_column("broadcast_campaigns", "media_file_id")
    op.drop_column("broadcast_campaigns", "media_type")
    op.drop_column("broadcast_campaigns", "audience")