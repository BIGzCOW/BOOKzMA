"""Track onboarding completion for the U-01 intro flow.

Existing users are backfilled from started_at so nobody sees the
onboarding flow twice after deploy; the KPI is meaningful from then on.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET onboarded_at = started_at WHERE started_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
