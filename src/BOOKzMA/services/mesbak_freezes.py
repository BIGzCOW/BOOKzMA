from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.repositories import mesbak, streak_freezes
from BOOKzMA.services.streak import compute_streak
from BOOKzMA.services.streak_freezes import FREEZE_CAP, FreezeChange, missed_day_to_protect

READS_PER_FREEZE = 7


async def on_completed_day(
    session: AsyncSession, user_id: int, today: date
) -> FreezeChange:
    await streak_freezes.lock_user(session, user_id)
    completed_days = await mesbak.completed_day_set(session, user_id)
    balance = await streak_freezes.balance(session, user_id, habit="mesbak")
    missed_day = missed_day_to_protect(completed_days, today)
    used_day = None
    if balance > 0 and missed_day is not None:
        if await streak_freezes.add_event(
            session, user_id, "used", missed_day, habit="mesbak"
        ):
            balance -= 1
            used_day = missed_day

    real_streak = compute_streak(completed_days, today)
    earned = False
    if real_streak > 0 and real_streak % READS_PER_FREEZE == 0 and balance < FREEZE_CAP:
        earned = await streak_freezes.add_event(
            session, user_id, "earned", today, habit="mesbak"
        )
    return FreezeChange(used_day=used_day, earned=earned)
