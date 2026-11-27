"""Rename the optional mesbak feature to mesbak.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_TABLES = (
    "profiles",
    "entries",
    "reminders",
    "badges",
    "challenges",
    "buddy_invites",
    "buddy_pairs",
)

_CONSTRAINTS = (
    ("profiles", "ck_miswak_profile_daily_goal", "ck_mesbak_profile_daily_goal"),
    ("profiles", "ck_miswak_profile_next_goal", "ck_mesbak_profile_next_goal"),
    ("entries", "ck_miswak_entry_slot", "ck_mesbak_entry_slot"),
    ("entries", "ck_miswak_entry_goal", "ck_mesbak_entry_goal"),
    ("entries", "ck_miswak_entry_slot_goal", "ck_mesbak_entry_slot_goal"),
    ("reminders", "ck_miswak_reminder_slot", "ck_mesbak_reminder_slot"),
    ("reminders", "uq_miswak_reminder_user_time", "uq_mesbak_reminder_user_time"),
    ("badges", "uq_miswak_badge_user_code", "uq_mesbak_badge_user_code"),
    ("challenges", "ck_miswak_challenge_duration", "ck_mesbak_challenge_duration"),
    ("challenges", "ck_miswak_challenge_status", "ck_mesbak_challenge_status"),
    ("buddy_pairs", "ck_miswak_buddy_pair_order", "ck_mesbak_buddy_pair_order"),
    ("buddy_pairs", "ck_miswak_buddy_pair_status", "ck_mesbak_buddy_pair_status"),
)

_INDEXES = (
    ("ix_miswak_entries_day", "ix_mesbak_entries_day"),
    ("uq_miswak_challenge_active_user", "uq_mesbak_challenge_active_user"),
    ("ix_miswak_buddy_invites_inviter", "ix_mesbak_buddy_invites_inviter"),
    ("uq_miswak_buddy_pair_active", "uq_mesbak_buddy_pair_active"),
)


def _rename_legacy_tables() -> None:
    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    for suffix in _TABLES:
        old_name = f"miswak_{suffix}"
        new_name = f"mesbak_{suffix}"
        if old_name in table_names and new_name not in table_names:
            op.rename_table(old_name, new_name)
            table_names.remove(old_name)
            table_names.add(new_name)


def upgrade() -> None:
    op.drop_constraint("ck_broadcast_campaign_audience", "broadcast_campaigns", type_="check")
    op.execute("UPDATE broadcast_campaigns SET audience = 'mesbak' WHERE audience = 'miswak'")
    op.create_check_constraint(
        "ck_broadcast_campaign_audience",
        "broadcast_campaigns",
        "audience IN ('all', 'mesbak')",
    )

    _rename_legacy_tables()

    for suffix, old_name, new_name in _CONSTRAINTS:
        table_name = f"mesbak_{suffix}"
        names = {
            item["name"]
            for item in (
                *sa.inspect(op.get_bind()).get_check_constraints(table_name),
                *sa.inspect(op.get_bind()).get_unique_constraints(table_name),
            )
        }
        if old_name in names and new_name not in names:
            op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')
    for old_name, new_name in _INDEXES:
        index_names = {
            item["name"]
            for suffix in _TABLES
            for item in sa.inspect(op.get_bind()).get_indexes(f"mesbak_{suffix}")
        }
        if old_name in index_names and new_name not in index_names:
            op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')


def downgrade() -> None:
    op.drop_constraint("ck_broadcast_campaign_audience", "broadcast_campaigns", type_="check")
    op.execute("UPDATE broadcast_campaigns SET audience = 'miswak' WHERE audience = 'mesbak'")
    op.create_check_constraint(
        "ck_broadcast_campaign_audience",
        "broadcast_campaigns",
        "audience IN ('all', 'miswak')",
    )

    for old_name, new_name in reversed(_INDEXES):
        index_names = {
            item["name"]
            for suffix in _TABLES
            for item in sa.inspect(op.get_bind()).get_indexes(f"mesbak_{suffix}")
        }
        if new_name in index_names and old_name not in index_names:
            op.execute(f'ALTER INDEX "{new_name}" RENAME TO "{old_name}"')
    for suffix, old_name, new_name in reversed(_CONSTRAINTS):
        table_name = f"mesbak_{suffix}"
        names = {
            item["name"]
            for item in (
                *sa.inspect(op.get_bind()).get_check_constraints(table_name),
                *sa.inspect(op.get_bind()).get_unique_constraints(table_name),
            )
        }
        if new_name in names and old_name not in names:
            op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{new_name}" TO "{old_name}"')

    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    for suffix in reversed(_TABLES):
        new_name = f"mesbak_{suffix}"
        old_name = f"miswak_{suffix}"
        if new_name in table_names and old_name not in table_names:
            op.rename_table(new_name, old_name)
            table_names.remove(new_name)
            table_names.add(old_name)
