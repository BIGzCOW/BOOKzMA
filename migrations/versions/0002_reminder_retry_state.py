"""Persist bounded reminder retry state.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reminders", sa.Column("attempt_date", sa.Date(), nullable=True))
    op.add_column(
        "reminders",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "reminders", sa.Column("retry_after_until", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reminders", "retry_after_until")
    op.drop_column("reminders", "attempt_count")
    op.drop_column("reminders", "attempt_date")
