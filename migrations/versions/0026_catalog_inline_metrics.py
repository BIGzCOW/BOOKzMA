"""Add inline search metrics to catalog usage days.

Revision ID: 0026
Revises: 0025
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

_OLD_CONSTRAINT = (
    "searches >= 0 AND result_pages >= 0 AND results_shown >= 0 "
    "AND empty_searches >= 0 AND downloads_succeeded >= 0 AND downloads_failed >= 0"
)
_NEW_CONSTRAINT = (
    "searches >= 0 AND result_pages >= 0 AND results_shown >= 0 "
    "AND empty_searches >= 0 AND downloads_succeeded >= 0 AND downloads_failed >= 0 "
    "AND inline_searches >= 0 AND inline_results_shown >= 0 AND inline_empty_searches >= 0"
)


def upgrade() -> None:
    op.add_column(
        "catalog_usage_days",
        sa.Column("inline_searches", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "catalog_usage_days",
        sa.Column("inline_results_shown", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "catalog_usage_days",
        sa.Column("inline_empty_searches", sa.Integer(), server_default="0", nullable=False),
    )
    op.drop_constraint(
        "ck_catalog_usage_day_nonnegative",
        "catalog_usage_days",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_usage_day_nonnegative",
        "catalog_usage_days",
        _NEW_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_catalog_usage_day_nonnegative",
        "catalog_usage_days",
        type_="check",
    )
    op.create_check_constraint(
        "ck_catalog_usage_day_nonnegative",
        "catalog_usage_days",
        _OLD_CONSTRAINT,
    )
    op.drop_column("catalog_usage_days", "inline_empty_searches")
    op.drop_column("catalog_usage_days", "inline_results_shown")
    op.drop_column("catalog_usage_days", "inline_searches")
