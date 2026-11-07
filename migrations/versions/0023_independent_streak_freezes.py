"""Separate Reading/Mesbak freezes and record admin gifts.

Revision ID: 0023
Revises: 0022
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "freeze_gift_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("habit", sa.String(length=16), nullable=False),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("requested_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("preview_recipients", sa.Integer(), server_default="0", nullable=False),
        sa.Column("preview_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("preview_capped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("preview_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credited_recipients", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credited_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("capped_recipients", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_recipients", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("habit IN ('reading', 'mesbak')", name="ck_freeze_gift_habit"),
        sa.CheckConstraint("audience IN ('all', 'mesbak')", name="ck_freeze_gift_audience"),
        sa.CheckConstraint("requested_amount BETWEEN 1 AND 1000", name="ck_freeze_gift_amount"),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'cancelled')", name="ck_freeze_gift_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "freeze_gift_recipients",
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("preview_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("credited_units", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.CheckConstraint("preview_units >= 0", name="ck_freeze_gift_preview_units"),
        sa.CheckConstraint("credited_units >= 0", name="ck_freeze_gift_credited_units"),
        sa.CheckConstraint(
            "status IN ('pending', 'credited', 'capped', 'skipped')",
            name="ck_freeze_gift_recipient_status",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["freeze_gift_operations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("operation_id", "user_id"),
    )
    op.create_index("ix_freeze_gift_recipients_user", "freeze_gift_recipients", ["user_id"])
    op.drop_constraint("uq_streak_freeze_user_kind_day", "streak_freezes", type_="unique")
    op.drop_constraint("ck_streak_freeze_kind", "streak_freezes", type_="check")
    op.add_column(
        "streak_freezes",
        sa.Column("habit", sa.String(length=16), server_default="reading", nullable=False),
    )
    op.add_column(
        "streak_freezes",
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column("streak_freezes", sa.Column("operation_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_streak_freezes_operation_id",
        "streak_freezes",
        "freeze_gift_operations",
        ["operation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_streak_freeze_kind", "streak_freezes", "kind IN ('earned', 'used', 'gifted')"
    )
    op.create_check_constraint(
        "ck_streak_freeze_habit", "streak_freezes", "habit IN ('reading', 'mesbak')"
    )
    op.create_check_constraint(
        "ck_streak_freeze_quantity", "streak_freezes", "quantity > 0"
    )
    op.create_check_constraint(
        "ck_streak_freeze_operation",
        "streak_freezes",
        "(kind = 'gifted' AND operation_id IS NOT NULL) OR "
        "(kind IN ('earned', 'used') AND operation_id IS NULL)",
    )
    op.create_index(
        "uq_streak_freeze_real_day",
        "streak_freezes",
        ["user_id", "habit", "kind", "day"],
        unique=True,
        postgresql_where=sa.text("kind IN ('earned', 'used')"),
    )
    op.create_unique_constraint(
        "uq_streak_freeze_operation_user", "streak_freezes", ["operation_id", "user_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_new_events = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM streak_freezes "
            "WHERE habit <> 'reading' OR kind = 'gifted') "
            "OR EXISTS (SELECT 1 FROM freeze_gift_operations)"
        )
    ).scalar_one()
    if has_new_events:
        raise RuntimeError("cannot downgrade after Mesbak freezes or freeze gift operations exist")

    op.drop_constraint("uq_streak_freeze_operation_user", "streak_freezes", type_="unique")
    op.drop_index("uq_streak_freeze_real_day", table_name="streak_freezes")
    op.drop_constraint("ck_streak_freeze_operation", "streak_freezes", type_="check")
    op.drop_constraint("ck_streak_freeze_quantity", "streak_freezes", type_="check")
    op.drop_constraint("ck_streak_freeze_habit", "streak_freezes", type_="check")
    op.drop_constraint("ck_streak_freeze_kind", "streak_freezes", type_="check")
    op.drop_constraint("fk_streak_freezes_operation_id", "streak_freezes", type_="foreignkey")
    op.drop_column("streak_freezes", "operation_id")
    op.drop_column("streak_freezes", "quantity")
    op.drop_column("streak_freezes", "habit")
    op.create_check_constraint(
        "ck_streak_freeze_kind", "streak_freezes", "kind IN ('earned', 'used')"
    )
    op.create_unique_constraint(
        "uq_streak_freeze_user_kind_day", "streak_freezes", ["user_id", "kind", "day"]
    )
    op.drop_index("ix_freeze_gift_recipients_user", table_name="freeze_gift_recipients")
    op.drop_table("freeze_gift_recipients")
    op.drop_table("freeze_gift_operations")