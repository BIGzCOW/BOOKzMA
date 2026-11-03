"""Add channel book catalog mirror and deferred page counts.

Revision ID: 0018
Revises: 0017
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "book_catalog_entries",
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=True),
        sa.Column("caption_preview", sa.String(length=512), nullable=True),
        sa.Column("caption_search", sa.Text(), server_default="", nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("posted_at", sa.String(length=64), nullable=True),
        sa.Column("bot_file_id", sa.String(length=512), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, coalesce(search_text, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("message_id"),
        sa.UniqueConstraint("source_row_id", name="uq_book_catalog_source_row"),
    )
    op.create_index(
        "ix_book_catalog_search_vector",
        "book_catalog_entries",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_book_catalog_file_name_message_id",
        "book_catalog_entries",
        ["file_name", "message_id"],
    )

    op.create_table(
        "book_catalog_sync_state",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("source_row_id", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("key"),
    )
    op.bulk_insert(
        sa.table("book_catalog_sync_state", sa.column("key", sa.String())),
        [{"key": "main"}],
    )

    op.drop_constraint("ck_user_book_total_pages", "user_books", type_="check")
    op.alter_column("user_books", "total_pages", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_user_book_total_pages",
        "user_books",
        "total_pages IS NULL OR total_pages BETWEEN 1 AND 100000",
    )
    op.add_column(
        "user_books",
        sa.Column("catalog_message_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_books_catalog_message_id",
        "user_books",
        "book_catalog_entries",
        ["catalog_message_id"],
        ["message_id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_user_book_catalog_message", "user_books", ["user_id", "catalog_message_id"]
    )
    op.drop_constraint("ck_user_book_status", "user_books", type_="check")
    op.create_check_constraint(
        "ck_user_book_status",
        "user_books",
        "status IN ('planned', 'reading', 'finished', 'archived')",
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM user_books WHERE total_pages IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade: user books have no page count';
            END IF;
        END $$
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM user_books WHERE status = 'planned') THEN
                RAISE EXCEPTION 'Cannot downgrade: planned books exist';
            END IF;
        END $$
        """
    )
    op.drop_constraint("ck_user_book_status", "user_books", type_="check")
    op.create_check_constraint(
        "ck_user_book_status",
        "user_books",
        "status IN ('reading', 'finished', 'archived')",
    )
    op.drop_constraint("uq_user_book_catalog_message", "user_books", type_="unique")
    op.drop_constraint("fk_user_books_catalog_message_id", "user_books", type_="foreignkey")
    op.drop_column("user_books", "catalog_message_id")
    op.drop_constraint("ck_user_book_total_pages", "user_books", type_="check")
    op.alter_column("user_books", "total_pages", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint(
        "ck_user_book_total_pages",
        "user_books",
        "total_pages BETWEEN 1 AND 100000",
    )
    op.drop_table("book_catalog_sync_state")
    op.drop_index("ix_book_catalog_file_name_message_id", table_name="book_catalog_entries")
    op.drop_index("ix_book_catalog_search_vector", table_name="book_catalog_entries")
    op.drop_table("book_catalog_entries")