from BOOKzMA import texts
from BOOKzMA.services.badges import FIRST_READ, COMEBACK_RESTORED, badge_label, badges_earned


def test_first_read_of_all_awards_first_read_badge():
    assert badges_earned(streak=1, total_read_days=1, comeback_restored=False) == [FIRST_READ]


def test_milestone_streaks_award_streak_badge():
    assert badges_earned(streak=3, total_read_days=5, comeback_restored=False) == ["streak_3"]
    assert badges_earned(streak=7, total_read_days=7, comeback_restored=False) == ["streak_7"]
    assert badges_earned(streak=30, total_read_days=30, comeback_restored=False) == ["streak_30"]


def test_non_milestone_days_award_nothing():
    assert badges_earned(streak=5, total_read_days=9, comeback_restored=False) == []


def test_comeback_restores_badge_comes_with_milestone():
    # ۳ روز پیاپی هم میلستون است هم لحظهٔ پاداش comeback
    codes = badges_earned(streak=3, total_read_days=3, comeback_restored=True)
    assert codes == ["streak_3", COMEBACK_RESTORED]


def test_badge_labels_are_friendly():
    assert badge_label(FIRST_READ).startswith("⭐")
    assert badge_label("streak_7") == "🔥 7 روز"
    assert badge_label(COMEBACK_RESTORED).startswith("🔁")


def test_badge_toast_line_and_empty():
    assert texts.badge_toast([]) is None
    line = texts.badge_toast([FIRST_READ])
    assert "اولین مطالعه" in line


def test_read_toast_appends_badge_line():
    toast = texts.read_toast(3, True, badges=["streak_3"])
    assert "نشان جدید" in toast
    plain = texts.read_toast(4, True)
    assert "نشان" not in plain
