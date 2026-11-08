"""Add catalog document fingerprints and Meilisearch outbox.

Revision ID: 0024
Revises: 0023
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "book_catalog_entries",
        sa.Column("document_hash", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "book_catalog_index_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=8), nullable=False),
        sa.Column("document", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "operation IN ('upsert', 'delete')", name="ck_book_catalog_outbox_op"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_book_catalog_outbox_message"),
    )
    op.create_index(
        "ix_book_catalog_outbox_created",
        "book_catalog_index_outbox",
        ["created_at", "id"],
    )


def downgrade() -> None:
    pending = op.get_bind().execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM book_catalog_index_outbox)")
    ).scalar_one()
    if pending:
        raise RuntimeError("cannot downgrade while catalog index operations are pending")

    op.drop_index("ix_book_catalog_outbox_created", table_name="book_catalog_index_outbox")
    op.drop_table("book_catalog_index_outbox")
    op.drop_column("book_catalog_entries", "document_hash")