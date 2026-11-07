from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from BOOKzMA.constants import MESBAK_PRESET_TIMES
from BOOKzMA.services.streak import compute_streak, longest_streak as calculate_longest_streak

MIN_DAILY_GOAL = 1
MAX_DAILY_GOAL = 5


def validate_daily_goal(goal: int) -> int:
    if (
        isinstance(goal, bool)
        or not isinstance(goal, int)
        or not MIN_DAILY_GOAL <= goal <= MAX_DAILY_GOAL
    ):
        raise ValueError("daily goal must be between 1 and 5")
    return goal


def validate_schedule(goal: int, times: Iterable[time]) -> list[time]:
    validate_daily_goal(goal)
    schedule = list(times)
    if len(schedule) != goal or len(set(schedule)) != goal:
        raise ValueError("schedule must contain one unique time for each daily occurrence")
    return schedule


def default_schedule(goal: int) -> list[time]:
    validate_daily_goal(goal)
    mapping = {
        1: ["22:00"],
        2: ["06:30", "22:00"],
        3: ["06:30", "13:00", "22:00"],
        4: ["06:30", "13:00", "19:00", "22:00"],
        5: ["06:30", "13:00", "16:00", "19:00", "22:00"],
    }
    return [time.fromisoformat(value) for value in mapping[goal]]


def is_legacy_default_schedule(goal: int, times: Iterable[time]) -> bool:
    validate_daily_goal(goal)
    legacy = [time.fromisoformat(value) for value in MESBAK_PRESET_TIMES[:goal]]
    return list(times) == legacy


def effective_goal(
    current_goal: int,
    next_goal: int | None,
    effective_on: date | None,
    today: date,
) -> int:
    validate_daily_goal(current_goal)
    if next_goal is not None and effective_on is not None and effective_on <= today:
        return validate_daily_goal(next_goal)
    return current_goal


def reminder_due(
    now: datetime,
    remind_at: time,
    last_sent_on: date | None,
    attempt_count: int,
    retry_after_until: datetime | None,
    max_late: timedelta = timedelta(minutes=10),
    max_attempts: int = 3,
) -> bool:
    today = now.date()
    if last_sent_on == today or attempt_count >= max_attempts:
        return False
    if retry_after_until is not None and retry_after_until > now:
        return False
    due = datetime.combine(today, remind_at, tzinfo=now.tzinfo)
    late = now - due
    return timedelta(0) <= late <= max_late



def next_occurrence(completed: Iterable[int], goal: int) -> int | None:
    validate_daily_goal(goal)
    completed_set = set(completed)
    return next((slot for slot in range(1, goal + 1) if slot not in completed_set), None)


def completed_days(records: Iterable[tuple[date, int, int]]) -> set[date]:
    return {
        day
        for day, completed_count, daily_goal in records
        if MIN_DAILY_GOAL <= daily_goal <= MAX_DAILY_GOAL and completed_count >= daily_goal
    }


def current_streak(
    days: Iterable[date], today: date, freeze_days: Iterable[date] = ()
) -> int:
    return compute_streak(days, today, freeze_days)


def longest_streak(days: Iterable[date], freeze_days: Iterable[date] = ()) -> int:
    return calculate_longest_streak(days, freeze_days)