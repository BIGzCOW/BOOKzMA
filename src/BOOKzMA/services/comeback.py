"""منطق Comeback streak (S-07): تشخیص شکست، دورهٔ بازگشت ۳ روزه و پاداش نیمی از استریک.

قواعد (spec در docs/specs/comeback-streak-at-risk.md):
- شکست استریک ≥۳ روزه بعد از غیبت، یک دورهٔ بازگشت باز می‌کند.
- ۳ روز پیاپی مطالعه بعد از شکست، `⌊شکسته ÷ ۲⌋` روز (سقف ۳۰) پاداش می‌دهد.
- پاداش فقط تا وقتی معتبر است که زنجیرهٔ همان دورهٔ بازگشت نشکسته باشد.
- `comeback_base_day` هم شروع پنجرهٔ بازگشت است هم مبنای اعتبار پاداش.
"""

from dataclasses import dataclass
from datetime import date

from BOOKzMA.services.streak import compute_streak, current_run_start

COMEBACK_MIN_BROKEN = 3
COMEBACK_DAYS = 3
COMEBACK_BONUS_CAP = 30


@dataclass
class ComebackChange:
    """چه پیامی باید نشان داده شود: شکست، پیشرفت، یا بازیابی."""

    broken_days: int = 0
    progress_done: int = 0
    bonus_added: int = 0


@dataclass
class ComebackState:
    bonus_days: int = 0
    bonus_base_day: date | None = None
    broken_streak_days: int | None = None


def restored_bonus(broken_days: int) -> int:
    return min(broken_days // 2, COMEBACK_BONUS_CAP)


def _previous_displayed(
    prev_days: set[date],
    frozen: set[date],
    bonus_days: int,
    bonus_base_day: date | None,
) -> int:
    """استریک نمایشی در آخرین روز قبل از شکست (پاداش قبلی هم محسوب)."""
    if not prev_days:
        return 0
    merged = prev_days | frozen
    reference = max(merged)
    raw = compute_streak(merged, reference)
    if bonus_days and bonus_base_day and current_run_start(merged, reference) == bonus_base_day:
        return raw + bonus_days
    return raw


def apply_read(
    *,
    days: set[date],
    frozen: set[date],
    today: date,
    state: ComebackState,
) -> tuple[ComebackState, ComebackChange]:
    """بعد از ثبت موفق مطالعهٔ امروز صدا زده می‌شود؛ state جدید و پیام برمی‌گرداند."""
    raw = compute_streak(days | frozen, today)
    if raw == 1:
        # امروز شروع تازه است: یا کاربر جدید است یا استریک شکسته
        prev_displayed = _previous_displayed(
            days - {today}, frozen, state.bonus_days, state.bonus_base_day
        )
        if prev_displayed >= COMEBACK_MIN_BROKEN:
            return (
                ComebackState(
                    bonus_days=state.bonus_days,
                    bonus_base_day=today,
                    broken_streak_days=prev_displayed,
                ),
                ComebackChange(broken_days=prev_displayed),
            )
        return ComebackState(), ComebackChange()

    if state.broken_streak_days is not None and state.bonus_base_day is not None:
        run_start = current_run_start(days | frozen, today)
        if run_start == state.bonus_base_day:
            if raw >= COMEBACK_DAYS:
                added = restored_bonus(state.broken_streak_days)
                return (
                    ComebackState(
                        bonus_days=state.bonus_days + added,
                        bonus_base_day=run_start,
                    ),
                    ComebackChange(bonus_added=added),
                )
            return state, ComebackChange(progress_done=raw)
    return state, ComebackChange()
