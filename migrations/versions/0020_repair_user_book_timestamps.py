"""Ensure personal-book lifecycle timestamps exist.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_books "
        "ADD COLUMN IF NOT EXISTS page_count_set_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE user_books "
        "ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    pass
