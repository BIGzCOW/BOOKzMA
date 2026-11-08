"""Track daily catalog usage aggregates.

Revision ID: 0025
Revises: 0024
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_usage_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("searches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result_pages", sa.Integer(), server_default="0", nullable=False),
        sa.Column("results_shown", sa.Integer(), server_default="0", nullable=False),
        sa.Column("empty_searches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("downloads_succeeded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("downloads_failed", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "searches >= 0 AND result_pages >= 0 AND results_shown >= 0 "
            "AND empty_searches >= 0 AND downloads_succeeded >= 0 AND downloads_failed >= 0",
            name="ck_catalog_usage_day_nonnegative",
        ),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("catalog_usage_days")