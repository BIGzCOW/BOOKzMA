from datetime import date, timedelta

from BOOKzMA.services.comeback import (
    COMEBACK_BONUS_CAP,
    ComebackState,
    apply_read,
    restored_bonus,
)
from BOOKzMA.services.risk_alert import is_at_risk
from BOOKzMA.services.streak import current_run_start, displayed_streak

TODAY = date(2026, 10, 25)


def d(days_from_today: int) -> date:
    return TODAY - timedelta(days=days_from_today)


def _range(start_ago: int, end_ago: int) -> set[date]:
    """مجموعه‌ای از روزها؛ آرگومان‌ها فاصله از امروزاند و end_ago کوچکتر است."""
    return {d(offset) for offset in range(start_ago, end_ago - 1, -1)}


def test_restored_bonus_is_half_capped():
    assert restored_bonus(7) == 3
    assert restored_bonus(60) == 30
    assert restored_bonus(80) == COMEBACK_BONUS_CAP
    assert restored_bonus(2) == 1


def test_first_read_of_new_user_has_no_comeback():
    state, change = apply_read(days={TODAY}, frozen=set(), today=TODAY, state=ComebackState())
    assert change.broken_days == 0
    assert state.broken_streak_days is None


def test_return_after_break_opens_comeback_window():
    days = _range(24, 15) | {TODAY}  # استریک ۱۰ روزه، ۱۴ روز غیبت، امروز خواند
    state, change = apply_read(days=days, frozen=set(), today=TODAY, state=ComebackState())
    assert change.broken_days == 10
    assert state.broken_streak_days == 10
    assert state.bonus_base_day == TODAY


def test_short_break_below_threshold_is_ignored():
    days = _range(24, 23) | {TODAY}  # استریک ۲ روزه شکست
    _state, change = apply_read(days=days, frozen=set(), today=TODAY, state=ComebackState())
    assert change.broken_days == 0


def test_progress_messages_during_window():
    day1 = TODAY - timedelta(days=2)
    yesterday = TODAY - timedelta(days=1)
    state = ComebackState(broken_streak_days=10, bonus_base_day=day1)
    days2 = {day1, yesterday}
    _state2, change2 = apply_read(
        days=days2, frozen=set(), today=yesterday, state=state
    )
    assert change2.progress_done == 2

    days3 = days2 | {TODAY}
    state3, change3 = apply_read(days=days3, frozen=set(), today=TODAY, state=state)
    assert change3.bonus_added == 5
    assert state3.bonus_days == 5
    assert state3.bonus_base_day == day1
    assert state3.broken_streak_days is None


def test_displayed_streak_includes_bonus_until_chain_breaks():
    day1 = TODAY - timedelta(days=2)
    days = {day1, TODAY - timedelta(days=1), TODAY}
    assert displayed_streak(days, TODAY, (), 5, day1) == 8
    # زنجیره شکست: روز دوم غیبت، بعد از اون روز تازه
    days2 = {day1, TODAY, TODAY - timedelta(days=1)}  # بدون شکست برای کنترل
    assert displayed_streak(days2, TODAY, (), 5, day1) == 8
    broken = {day1, TODAY - timedelta(days=3)} | {TODAY}  # زنجیرهٔ جدید از امروز
    assert displayed_streak(broken, TODAY, (), 5, day1) == 1


def test_bonus_is_base_for_next_comeback_after_new_break():
    day1 = TODAY - timedelta(days=2)
    days = {day1, TODAY - timedelta(days=1), TODAY}
    state = ComebackState(bonus_days=5, bonus_base_day=day1)
    # بعد از زنجیرهٔ پاداش‌دار، غیبت و بازگشت
    later = TODAY + timedelta(days=10)
    returning = days | {later}
    state2, change = apply_read(
        days=returning, frozen=set(), today=later, state=state
    )
    assert change.broken_days == 8  # ۳ روز واقعی + ۵ پاداش
    assert state2.broken_streak_days == 8


def test_current_run_start():
    days = _range(24, 0)
    assert current_run_start(days, TODAY) == d(24)
    assert current_run_start(set(), TODAY) is None
    # زنجیره از وسط گسسته؛ فقط آخرین بخش شمارده می‌شود
    gapped = {d(5), d(4), d(2), d(1)}
    assert current_run_start(gapped, TODAY) == d(2)


def test_is_at_risk_requires_unbroken_streak_and_no_read_today():
    streak = _range(2, 1)  # دیروز و پیش‌دیروز
    assert is_at_risk(TODAY, streak, set()) is True
    assert is_at_risk(TODAY, streak | {TODAY}, set()) is False  # امروز خوانده
    assert is_at_risk(TODAY, {d(1)}, set()) is False  # استریک ۱ روزه
    assert is_at_risk(TODAY, _range(5, 3), set()) is False  # از پریروز قطع شده


def test_frozen_day_keeps_streak_at_risk_eligible():
    reads = {d(2)}
    frozen_yesterday = {d(1)}
    assert is_at_risk(TODAY, reads, frozen_yesterday) is True
