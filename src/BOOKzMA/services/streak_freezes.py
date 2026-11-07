from dataclasses import dataclass
from datetime import date, timedelta
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.repositories import readings, streak_freezes
from BOOKzMA.services.streak import compute_streak

FREEZE_CAP = 3
READS_PER_FREEZE = 7


@dataclass(frozen=True)
class FreezeChange:
    used_day: date | None = None
    earned: bool = False


def missed_day_to_protect(read_days: Iterable[date], today: date) -> date | None:
    day_set = set(read_days)
    missed_day = today - timedelta(days=1)
    previous_day = today - timedelta(days=2)
    if today in day_set and missed_day not in day_set and previous_day in day_set:
        return missed_day
    return None


def should_earn_freeze(real_streak: int, balance: int) -> bool:
    return real_streak > 0 and real_streak % READS_PER_FREEZE == 0 and balance < FREEZE_CAP


async def on_read(session: AsyncSession, user_id: int, today: date) -> FreezeChange:
    await streak_freezes.lock_user(session, user_id)
    read_days = await readings.get_days(session, user_id)
    balance = await streak_freezes.balance(session, user_id)
    used_day = None

    missed_day = missed_day_to_protect(read_days, today)
    if balance > 0 and missed_day is not None:
        if await streak_freezes.add_event(session, user_id, "used", missed_day):
            balance -= 1
            used_day = missed_day

    real_streak = compute_streak(read_days, today)
    earned = False
    if should_earn_freeze(real_streak, balance):
        earned = await streak_freezes.add_event(session, user_id, "earned", today)

    return FreezeChange(used_day=used_day, earned=earned)