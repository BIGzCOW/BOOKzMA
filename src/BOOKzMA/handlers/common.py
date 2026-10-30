from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.db.models import User
from BOOKzMA.repositories import buddy as buddy_repo
from BOOKzMA.repositories import readings, users
from BOOKzMA.repositories import streak_freezes
from BOOKzMA.repositories import mesbak as mesbak_repo
from BOOKzMA.services.mesbak import completed_days, current_streak
from BOOKzMA.services.buddy_nudges import classify_nudge_targets
from BOOKzMA.services.streak import displayed_streak, longest_streak, week_strip
from BOOKzMA.utils import local_today


async def show(
    event: Message | CallbackQuery, text: str, kb: InlineKeyboardMarkup | None
) -> None:
    """دکمه‌ها پیام قبلی رو ویرایش می‌کنن، پیام جدید رو می‌فرستیم"""
    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb)
        return
    if isinstance(event.message, Message):
        try:
            await event.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise


async def render_home(event: Message | CallbackQuery, session: AsyncSession, tg: TgUser) -> None:
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    today = local_today(user.timezone)
    mesbak_profile = await mesbak_repo.get_profile(session, user.id, today)
    mesbak_streak = None
    if mesbak_profile is not None and mesbak_profile.enabled:
        mesbak_streak = current_streak(
            completed_days(await mesbak_repo.daily_records(session, user.id)), today
        )
    await session.commit()
    days = set(await readings.get_days(session, user.id))
    frozen_days = set(await streak_freezes.used_days(session, user.id))
    freeze_balance = await streak_freezes.balance(session, user.id)
    read_today = today in days
    text = texts.home(
        displayed_streak(
            days, today, frozen_days, user.comeback_bonus_days, user.comeback_base_day
        ),
        longest_streak(days, frozen_days),
        week_strip(days, today, frozen_days),
        read_today,
        freeze_balance,
        mesbak_streak,
    )
    await show(
        event,
        text,
        keyboards.home_kb(read_today, mesbak_profile is not None and mesbak_profile.enabled),
    )


async def offer_buddy_nudge(
    message: Message | None, session: AsyncSession, user: User
) -> None:
    if message is None:
        return
    buddies = await buddy_repo.active_buddy_users(session, user.id)
    if not buddies:
        return
    read_user_ids = await readings.users_read_on_days(
        session,
        [(buddy.id, local_today(buddy.timezone)) for _pair, buddy in buddies],
    )
    targets, _already_read, _already_nudged = classify_nudge_targets(
        buddies, read_user_ids, local_today(user.timezone)
    )
    if targets:
        await message.answer(
            texts.BUDDY_NUDGE_PROMPT,
            reply_markup=keyboards.buddy_nudge_prompt_kb(),
        )
