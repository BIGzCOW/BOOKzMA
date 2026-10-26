from collections.abc import Iterable
from datetime import date, timedelta


def compute_streak(
    days: Iterable[date], today: date, freeze_days: Iterable[date] = ()
) -> int:
    # اگه امروز هنوز نخونده ولی دیروز خونده، استریک تا آخر امروز زنده‌ست
    day_set = set(days) | set(freeze_days)
    cursor = today if today in day_set else today - timedelta(days=1)
    count = 0
    while cursor in day_set:
        count += 1
        cursor -= timedelta(days=1)
    return count


def current_run_start(
    days: Iterable[date], today: date, freeze_days: Iterable[date] = ()
) -> date | None:
    """روز شروع زنجیرهٔ پیوستهٔ جاری؛ None یعنی استریک فعلی صفر است."""
    day_set = set(days) | set(freeze_days)
    cursor = today if today in day_set else today - timedelta(days=1)
    if cursor not in day_set:
        return None
    start = cursor
    while start - timedelta(days=1) in day_set:
        start -= timedelta(days=1)
    return start


def displayed_streak(
    days: Iterable[date],
    today: date,
    freeze_days: Iterable[date] = (),
    bonus_days: int = 0,
    bonus_base_day: date | None = None,
) -> int:
    """استریک واقعی + پاداش comeback، فقط تا وقتی زنجیرهٔ همان دوره نشکسته."""
    raw = compute_streak(days, today, freeze_days)
    if not bonus_days or not bonus_base_day:
        return raw
    if current_run_start(days, today, freeze_days) == bonus_base_day:
        return raw + bonus_days
    return raw


def longest_streak(days: Iterable[date], freeze_days: Iterable[date] = ()) -> int:
    best = run = 0
    prev: date | None = None
    for d in sorted(set(days) | set(freeze_days)):
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def week_strip(days: Iterable[date], today: date, freeze_days: Iterable[date] = ()) -> str:
    # هفت روز آخر، آخری امروزه
    day_set = set(days)
    frozen_set = set(freeze_days)
    cells = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        if d in day_set:
            cells.append("✅")
        elif d in frozen_set:
            cells.append("🛡️")
        elif d == today:
            cells.append("🟡")
        else:
            cells.append("▫️")
    return " ".join(cells)


def weekly_summary(
    days: Iterable[date], today: date, freeze_days: Iterable[date] = ()
) -> dict[str, object]:
    day_set = set(days)
    frozen_set = set(freeze_days)
    week_days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    read_days = [day for day in week_days if day in day_set]
    return {
        "start": week_days[0],
        "end": week_days[-1],
        "days_read": len(read_days),
        "streak": compute_streak(day_set, today, frozen_set),
        "days": [
            {"date": day, "read": day in day_set, "frozen": day in frozen_set}
            for day in week_days
        ],
    }
