from datetime import date, timedelta

from BOOKzMA.services.streak import compute_streak, longest_streak, week_strip, weekly_summary
from BOOKzMA.services.streak_freezes import missed_day_to_protect, should_earn_freeze

TODAY = date(2026, 10, 21)


def ago(n):
    return TODAY - timedelta(days=n)


def test_empty():
    assert compute_streak([], TODAY) == 0


def test_today_and_before():
    assert compute_streak([ago(0), ago(1), ago(2)], TODAY) == 3


def test_only_yesterday_keeps_streak():
    assert compute_streak([ago(1), ago(2)], TODAY) == 2


def test_missed_a_day_resets():
    assert compute_streak([ago(2), ago(3)], TODAY) == 0


def test_freeze_bridges_one_missed_day():
    assert compute_streak([ago(0), ago(2)], TODAY, [ago(1)]) == 3


def test_freeze_does_not_bridge_multiple_missed_days():
    assert compute_streak([ago(0), ago(3)], TODAY, [ago(2)]) == 1


def test_gap_stops_the_count():
    assert compute_streak([ago(0), ago(1), ago(3), ago(4)], TODAY) == 2


def test_duplicates_ignored():
    assert compute_streak([ago(0), ago(0), ago(1)], TODAY) == 2


def test_longest():
    assert longest_streak([]) == 0
    assert longest_streak([ago(0), ago(1), ago(5), ago(6), ago(7), ago(8)]) == 4
    assert longest_streak([ago(0), ago(2)], [ago(1)]) == 3


def test_week_strip():
    assert week_strip([ago(0), ago(1)], TODAY) == "▫️ ▫️ ▫️ ▫️ ▫️ ✅ ✅"
    assert week_strip([ago(1)], TODAY) == "▫️ ▫️ ▫️ ▫️ ▫️ ✅ 🟡"
    assert week_strip([ago(0)], TODAY, [ago(1)]) == "▫️ ▫️ ▫️ ▫️ ▫️ 🛡️ ✅"


def test_weekly_summary_counts_only_the_last_seven_days():
    summary = weekly_summary([ago(0), ago(2), ago(6), ago(7)], TODAY)

    assert summary["start"] == ago(6)
    assert summary["end"] == TODAY
    assert summary["days_read"] == 3
    assert summary["streak"] == 1
    assert len(summary["days"]) == 7


def test_weekly_summary_keeps_freeze_out_of_read_count():
    summary = weekly_summary([ago(0), ago(2)], TODAY, [ago(1)])

    assert summary["days_read"] == 2
    assert summary["streak"] == 3
    assert summary["days"][5] == {"date": ago(1), "read": False, "frozen": True}


def test_freeze_protects_only_one_missed_day_after_reading_resumes():
    assert missed_day_to_protect([ago(0), ago(2)], TODAY) == ago(1)
    assert missed_day_to_protect([ago(0), ago(3)], TODAY) is None
    assert missed_day_to_protect([ago(2)], TODAY) is None


def test_freeze_reward_requires_seven_real_reads_and_room_in_inventory():
    assert should_earn_freeze(7, 0)
    assert should_earn_freeze(14, 1)
    assert not should_earn_freeze(6, 0)
    assert should_earn_freeze(7, 2)
    assert not should_earn_freeze(7, 3)
