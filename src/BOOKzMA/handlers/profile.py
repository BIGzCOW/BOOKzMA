import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers.common import show
from BOOKzMA.repositories import badges as badges_repo
from BOOKzMA.repositories import readings, streak_freezes, users
from BOOKzMA.repositories import miswak as miswak_repo
from BOOKzMA.services.miswak import completed_days, current_streak
from BOOKzMA.services.streak import displayed_streak, longest_streak
from BOOKzMA.utils import local_today

router = Router()
LEADERBOARD_LIMIT = 10


async def render_profile(event: Message | CallbackQuery, session: AsyncSession) -> None:
    tg = event.from_user if isinstance(event, Message) else event.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    today = local_today(user.timezone)
    miswak_profile = await miswak_repo.get_profile(session, user.id, today)
    miswak_streak = None
    if miswak_profile is not None and miswak_profile.enabled:
        miswak_streak = current_streak(
            completed_days(await miswak_repo.daily_records(session, user.id)), today
        )
    await session.commit()
    days = await readings.get_days(session, user.id)
    frozen_days = await streak_freezes.used_days(session, user.id)
    await show(
        event,
        texts.profile(
            displayed_streak(
                days,
                local_today(user.timezone),
                frozen_days,
                user.comeback_bonus_days,
                user.comeback_base_day,
            ),
            longest_streak(days, frozen_days),
            await streak_freezes.balance(session, user.id),
            user.leaderboard_opt_out,
            await badges_repo.list_for_user(session, user.id),
            miswak_streak,
        ),
        keyboards.profile_kb(
            user.leaderboard_opt_out, miswak_profile is not None and miswak_profile.enabled
        ),
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 پروفایل")
async def on_profile(message: Message, session: AsyncSession) -> None:
    await render_profile(message, session)


@router.callback_query(F.data == "leaderboard:toggle")
async def on_leaderboard_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    opt_out = not user.leaderboard_opt_out
    await users.set_leaderboard_opt_out(session, user.id, opt_out)
    await session.commit()
    await callback.answer("از لیدربورد خارج شدی" if opt_out else "در لیدربورد حضور داری")
    await render_profile(callback, session)


@router.callback_query(F.data == "leaderboard")
async def on_leaderboard(callback: CallbackQuery, session: AsyncSession) -> None:
    rows = await users.leaderboard_rows(session)
    scores = []
    for _user_id, display_name, timezone_name, bonus_days, bonus_base, days, frozen_days in rows:
        current = displayed_streak(
            days, local_today(timezone_name), frozen_days, bonus_days, bonus_base
        )
        if current:
            scores.append((current, (display_name or "کتاب‌خوان").replace("\n", " ")))
    scores.sort(key=lambda row: (-row[0], row[1]))
    if not scores:
        text = "🏅 <b>لیدربورد استریک</b>\n\nهنوز استریکی برای نمایش نیست."
    else:
        lines = ["🏅 <b>لیدربورد استریک</b>"]
        for rank, (streak, display_name) in enumerate(scores[:LEADERBOARD_LIMIT], 1):
            lines.append(f"{rank}. {escape(display_name)} · {streak} روز")
        text = "\n".join(lines)
    current_user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    today = local_today(current_user.timezone)
    miswak_profile = await miswak_repo.get_profile(session, current_user.id, today)
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.profile_kb(
                current_user.leaderboard_opt_out,
                miswak_profile is not None and miswak_profile.enabled,
            ),
        )


@router.message(Command("support"))
@router.message(F.text == "💚 حمایت از پروژه")
async def on_support(message: Message, settings: Settings) -> None:
    support_username = settings.support_telegram_username.strip().removeprefix("@")
    support_url = f"https://t.me/{support_username}" if re.fullmatch(
        r"[A-Za-z0-9_]{5,32}", support_username
    ) else ""
    github_url = settings.github_url.strip()
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", github_url):
        github_url = ""
    await message.answer(
        texts.support(), reply_markup=keyboards.support_kb(github_url, support_url)
    )