from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import User
from BOOKzMA.repositories import badges as badges_repo
from BOOKzMA.repositories import readings, streak_freezes
from BOOKzMA.services.badges import badges_earned
from BOOKzMA.services.comeback import ComebackChange, ComebackState, apply_read
from BOOKzMA.services.streak import displayed_streak
from BOOKzMA.services.streak_freezes import FreezeChange
from BOOKzMA.services.streak_freezes import on_read as apply_streak_freeze


@dataclass(frozen=True)
class ReadingRegistration:
    created: bool
    streak: int
    freeze_change: FreezeChange | None
    freeze_balance: int
    comeback_change: ComebackChange | None
    badges: tuple[str, ...]


async def register_reading(
    session: AsyncSession, user: User, today: date
) -> ReadingRegistration:
    created = await readings.mark_read(session, user.id, today)
    freeze_change = None
    comeback_change = None
    new_badges: list[str] = []
    if created:
        freeze_change = await apply_streak_freeze(session, user.id, today)
        days = set(await readings.get_days(session, user.id))
        frozen_days = set(await streak_freezes.used_days(session, user.id))
        new_state, comeback_change = apply_read(
            days=days,
            frozen=frozen_days,
            today=today,
            state=ComebackState(
                bonus_days=user.comeback_bonus_days,
                bonus_base_day=user.comeback_base_day,
                broken_streak_days=user.broken_streak_days,
            ),
        )
        user.broken_streak_days = new_state.broken_streak_days
        user.comeback_bonus_days = new_state.bonus_days
        user.comeback_base_day = new_state.bonus_base_day
        streak_now = displayed_streak(
            days, today, frozen_days, new_state.bonus_days, new_state.bonus_base_day
        )
        for code in badges_earned(
            streak=streak_now,
            total_read_days=len(days),
            comeback_restored=comeback_change.bonus_added > 0,
        ):
            if await badges_repo.award(session, user.id, code, today):
                new_badges.append(code)

    days = await readings.get_days(session, user.id)
    frozen_days = await streak_freezes.used_days(session, user.id)
    return ReadingRegistration(
        created=created,
        streak=displayed_streak(
            days,
            today,
            frozen_days,
            user.comeback_bonus_days,
            user.comeback_base_day,
        ),
        freeze_change=freeze_change,
        freeze_balance=await streak_freezes.balance(session, user.id),
        comeback_change=comeback_change,
        badges=tuple(new_badges),
    )
