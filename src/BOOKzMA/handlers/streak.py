from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.handlers.common import render_home
from BOOKzMA.repositories import badges as badges_repo
from BOOKzMA.repositories import buddy as buddy_repo
from BOOKzMA.repositories import readings, users
from BOOKzMA.repositories import streak_freezes
from BOOKzMA.services.badges import badges_earned
from BOOKzMA.services.comeback import ComebackState, apply_read
from BOOKzMA.services.streak import displayed_streak
from BOOKzMA.services.streak_freezes import on_read as apply_streak_freeze
from BOOKzMA.utils import local_today
from BOOKzMA.services.buddy_nudges import classify_nudge_targets

router = Router()


@router.callback_query(F.data == "read")
async def on_read(callback: CallbackQuery, session: AsyncSession) -> None:
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username)
    today = local_today(user.timezone)
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
    await session.commit()

    days = await readings.get_days(session, user.id)
    frozen_days = await streak_freezes.used_days(session, user.id)
    streak = displayed_streak(
        days, today, frozen_days, user.comeback_bonus_days, user.comeback_base_day
    )
    toast = texts.read_toast(
        streak,
        created,
        freeze_used=freeze_change is not None and freeze_change.used_day is not None,
        freeze_earned=freeze_change is not None and freeze_change.earned,
        freeze_balance=await streak_freezes.balance(session, user.id),
        comeback=texts.comeback_line(comeback_change, streak),
        badges=new_badges,
    )
    await callback.answer(toast)
    await render_home(callback, session, tg)
    if created:
        buddies = await buddy_repo.active_buddy_users(session, user.id)
        if buddies:
            nudge_day = local_today(user.timezone)
            read_user_ids = await readings.users_read_on_days(
                session,
                [(buddy.id, local_today(buddy.timezone)) for _pair, buddy in buddies],
            )
            targets, _already_read, _already_nudged = classify_nudge_targets(
                buddies, read_user_ids, nudge_day
            )
            if targets and isinstance(callback.message, Message):
                await callback.message.answer(
                    texts.BUDDY_NUDGE_PROMPT,
                    reply_markup=keyboards.buddy_nudge_prompt_kb(),
                )
