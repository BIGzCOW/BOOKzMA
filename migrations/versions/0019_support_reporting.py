"""Track support metadata and page-count updates.

Revision ID: 0019
Revises: 0018
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_books",
        sa.Column("page_count_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_books",
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "support_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_support_ticket_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_tickets_user_status", "support_tickets", ["user_id", "status"]
    )
    op.create_table(
        "support_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('user_message', 'admin_reply')", name="ck_support_event_kind"
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_events_created_at", "support_events", ["created_at"])
    op.create_index("ix_support_events_ticket_id", "support_events", ["ticket_id"])
    op.create_table(
        "support_blocks",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "blocked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("support_blocks")
    op.drop_index("ix_support_events_ticket_id", table_name="support_events")
    op.drop_index("ix_support_events_created_at", table_name="support_events")
    op.drop_table("support_events")
    op.drop_index("ix_support_tickets_user_status", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_column("user_books", "restored_at")
    op.drop_column("user_books", "page_count_set_at")