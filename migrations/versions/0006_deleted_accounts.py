"""Track deleted accounts so removed users are not silently re-registered.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deleted_accounts",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("deleted_accounts")
