"""Add personal library and page logs.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="reading", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "total_pages BETWEEN 1 AND 100000", name="ck_user_book_total_pages"
        ),
        sa.CheckConstraint(
            "status IN ('reading', 'finished', 'archived')", name="ck_user_book_status"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_books_user_status", "user_books", ["user_id", "status"]
    )
    op.create_table(
        "page_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_book_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("pages_read", sa.Integer(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "pages_read BETWEEN 1 AND 100000", name="ck_page_log_pages_read"
        ),
        sa.ForeignKeyConstraint(["user_book_id"], ["user_books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_book_id",
            "source_message_id",
            name="uq_page_log_book_source_message",
        ),
    )
    op.create_index("ix_page_logs_day", "page_logs", ["day"])


def downgrade() -> None:
    op.drop_index("ix_page_logs_day", table_name="page_logs")
    op.drop_table("page_logs")
    op.drop_index("ix_user_books_user_status", table_name="user_books")
    op.drop_table("user_books")
