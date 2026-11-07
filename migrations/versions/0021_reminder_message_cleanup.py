"""Track reminder message deliveries for completion cleanup.

Revision ID: 0021
Revises: 0020
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reminder_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("habit", sa.String(length=16), nullable=False),
        sa.Column("schedule_id", sa.Integer(), nullable=False),
        sa.Column("local_day", sa.Date(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("cleanup_pending", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("retry_after_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("habit IN ('reading', 'mesbak')", name="ck_reminder_message_habit"),
        sa.CheckConstraint("schedule_id > 0", name="ck_reminder_message_schedule_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_reminder_message_user_message"),
    )
    op.create_index(
        "ix_reminder_messages_owner_day",
        "reminder_messages",
        ["user_id", "habit", "local_day"],
    )
    op.create_index(
        "ix_reminder_messages_pending",
        "reminder_messages",
        ["retry_after_until"],
        postgresql_where=sa.text("cleanup_pending"),
    )


def downgrade() -> None:
    op.drop_index("ix_reminder_messages_pending", table_name="reminder_messages")
    op.drop_index("ix_reminder_messages_owner_day", table_name="reminder_messages")
    op.drop_table("reminder_messages")