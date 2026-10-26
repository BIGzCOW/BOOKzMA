"""Allow users to have multiple active study buddies.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_buddy_pair_user_b_active", table_name="buddy_pairs")
    op.drop_index("uq_buddy_pair_user_a_active", table_name="buddy_pairs")
    op.create_index(
        "uq_buddy_pair_active_pair",
        "buddy_pairs",
        ["user_a", "user_b"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    duplicate_users = op.get_bind().execute(
        sa.text(
            "SELECT user_id FROM ("
            "SELECT user_a AS user_id FROM buddy_pairs WHERE status = 'active' "
            "UNION ALL "
            "SELECT user_b AS user_id FROM buddy_pairs WHERE status = 'active'"
            ") AS active_users GROUP BY user_id HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate_users is not None:
        raise RuntimeError("Cannot downgrade while users have multiple active study buddies")

    op.drop_index("uq_buddy_pair_active_pair", table_name="buddy_pairs")
    op.create_index(
        "uq_buddy_pair_user_a_active",
        "buddy_pairs",
        ["user_a"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_buddy_pair_user_b_active",
        "buddy_pairs",
        ["user_b"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )