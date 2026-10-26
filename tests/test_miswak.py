from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from BOOKzMA import keyboards, texts
from BOOKzMA.services.miswak import (
    completed_days,
    current_streak,
    default_schedule,
    effective_goal,
    longest_streak,
    is_legacy_default_schedule,
    next_occurrence,
    reminder_due,
    validate_daily_goal,
    validate_schedule,
)
from BOOKzMA.services.miswak_social import (
    challenge_failed,
    challenge_end_date,
    challenge_progress,
    invite_token_hash,
    new_invite_token,
)

TODAY = date(2026, 10, 26)


@pytest.mark.parametrize("goal", [1, 2, 3, 4, 5])
def test_daily_goal_accepts_one_through_five(goal):
    assert validate_daily_goal(goal) == goal


@pytest.mark.parametrize("goal", [0, 6, -1, True, "2"])
def test_daily_goal_rejects_out_of_range_values(goal):
    with pytest.raises(ValueError):
        validate_daily_goal(goal)


def test_next_occurrence_skips_completed_slots_and_stops_at_goal():
    assert next_occurrence([], 1) == 1
    assert next_occurrence([1, 3], 5) == 2
    assert next_occurrence([1, 2, 3, 4, 5], 5) is None


def test_schedule_requires_one_unique_time_per_occurrence():
    assert validate_schedule(2, [time(6, 30), time(13)]) == [time(6, 30), time(13)]
    with pytest.raises(ValueError):
        validate_schedule(2, [time(6, 30)])
    with pytest.raises(ValueError):
        validate_schedule(2, [time(6, 30), time(6, 30)])


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        (1, [time(22)]),
        (2, [time(19), time(22)]),
        (5, [time(6, 30), time(13), time(16), time(19), time(22)]),
    ],
)
def test_default_schedule_uses_latest_times_for_smaller_goals(goal, expected):
    assert default_schedule(goal) == expected


def test_legacy_default_schedule_is_detected_without_reclassifying_custom_times():
    assert is_legacy_default_schedule(1, [time(6, 30)])
    assert not is_legacy_default_schedule(1, [time(7, 30)])


def test_goal_change_takes_effect_on_its_local_effective_date():
    tomorrow = TODAY + timedelta(days=1)
    assert effective_goal(2, 4, tomorrow, TODAY) == 2
    assert effective_goal(2, 4, tomorrow, tomorrow) == 4
    assert effective_goal(2, 4, TODAY, TODAY) == 4


def test_only_days_that_reach_their_snapshot_goal_are_completed():
    records = [
        (TODAY, 1, 1),
        (TODAY - timedelta(days=1), 2, 3),
        (TODAY - timedelta(days=2), 5, 5),
        (TODAY - timedelta(days=3), 0, 0),
    ]

    assert completed_days(records) == {TODAY, TODAY - timedelta(days=2)}


def test_current_streak_includes_yesterday_until_today_ends():
    days = {TODAY - timedelta(days=1), TODAY - timedelta(days=2)}

    assert current_streak(days, TODAY) == 2
    assert current_streak(days | {TODAY}, TODAY) == 3


def test_missed_day_breaks_current_streak():
    assert current_streak({TODAY - timedelta(days=2), TODAY - timedelta(days=3)}, TODAY) == 0


def test_longest_streak_is_derived_from_completed_days():
    days = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=4)}

    assert longest_streak(days) == 2
    assert longest_streak([]) == 0


def test_challenge_duration_and_consecutive_progress():
    assert challenge_end_date(TODAY, 7) == TODAY + timedelta(days=6)
    with pytest.raises(ValueError):
        challenge_end_date(TODAY, 14)
    assert (
        challenge_progress(
            {TODAY, TODAY + timedelta(days=1)}, TODAY, TODAY + timedelta(days=2)
        )
        == 2
    )
    assert challenge_progress({TODAY + timedelta(days=1)}, TODAY, TODAY + timedelta(days=2)) == 0


def test_challenge_fails_after_a_closed_day_is_missed_but_not_during_today():
    yesterday = TODAY - timedelta(days=1)
    assert not challenge_failed({TODAY}, TODAY, TODAY + timedelta(days=6), TODAY)
    assert challenge_failed(
        {TODAY, TODAY + timedelta(days=2)}, TODAY, TODAY + timedelta(days=6),
        TODAY + timedelta(days=3),
    )
    assert not challenge_failed(
        {TODAY, yesterday}, yesterday, yesterday + timedelta(days=6), TODAY
    )


def test_miswak_invite_token_is_validated_and_hashed():
    token = new_invite_token()

    assert invite_token_hash(token) is not None
    assert invite_token_hash(token) == invite_token_hash(token)
    assert invite_token_hash("../../bad") is None


def test_miswak_screen_shows_independent_badges():
    screen = texts.miswak_screen(1, 1, 7, 7, ["06:30"], None, None, ["streak_7"])

    assert "🏅 دستاوردها: ۷ روز" in screen


def test_miswak_buddy_button_labels_are_bounded_and_single_line():
    keyboard = keyboards.miswak_buddy_list_kb([(1, "نام\n" + "x" * 100)])
    nudge_label = keyboard.inline_keyboard[0][0].text

    assert "\n" not in nudge_label
    assert len(nudge_label) <= 64


def test_miswak_goal_keyboard_has_valid_rows_and_callbacks():
    keyboard = keyboards.miswak_goal_kb()

    assert len(keyboard.inline_keyboard) == 2
    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == [
        f"miswak:goal:{goal}" for goal in range(1, 6)
    ]
    assert keyboard.inline_keyboard[1][0].callback_data == "miswak:open"


def test_reminder_due_respects_late_window_retry_and_daily_dedup():
    now = datetime(2026, 10, 26, 6, 40, tzinfo=ZoneInfo("Asia/Tehran"))

    assert reminder_due(now, time(6, 30), None, 0, None)
    assert not reminder_due(now, time(6, 29), TODAY, 0, None)
    assert not reminder_due(now, time(6, 0), None, 0, None)
    assert not reminder_due(now, time(6, 30), None, 3, None)
    assert not reminder_due(now, time(6, 30), None, 1, now + timedelta(minutes=1))


def test_nonexistent_dst_wall_time_is_not_sent_late():
    now = datetime(2026, 3, 8, 3, 5, tzinfo=ZoneInfo("America/New_York"))

    assert not reminder_due(now, time(2, 30), None, 0, None)


def test_ambiguous_dst_reminder_is_suppressed_after_first_fold_send():
    first_fold = datetime(
        2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=0
    )
    second_fold = first_fold.replace(fold=1)

    assert reminder_due(first_fold, time(1, 30), None, 0, None)
    assert not reminder_due(second_fold, time(1, 30), first_fold.date(), 1, None)