import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.handlers.common import show
from BOOKzMA.handlers.miswak import render_miswak
from BOOKzMA.db.models import User
from BOOKzMA.repositories import miswak as miswak_repo
from BOOKzMA.repositories import users
from BOOKzMA.services.miswak_social import invite_token_hash, new_invite_token
from BOOKzMA.utils import local_today

router = Router()
log = logging.getLogger(__name__)
INVITE_PREFIX = "miswakbuddy_"


async def _active_user(session: AsyncSession, tg_user) -> tuple[User, date] | None:
    user = await users.get_or_create(
        session, tg_user.id, tg_user.username, tg_user.full_name
    )
    today = local_today(user.timezone)
    profile = await miswak_repo.get_profile(session, user.id, today)
    if profile is None or not profile.enabled:
        return None
    return user, today


async def redeem_start_invite(
    session: AsyncSession, recipient_id: int, payload: str
) -> tuple[str, int | None]:
    if not payload.startswith(INVITE_PREFIX):
        return "unavailable", None
    token_hash = invite_token_hash(payload.removeprefix(INVITE_PREFIX))
    if token_hash is None:
        return "unavailable", None
    return await miswak_repo.redeem_buddy_invite(
        session, token_hash, recipient_id, datetime.now(timezone.utc)
    )


@router.callback_query(F.data.startswith("miswak:challenge:start:"))
async def on_challenge_start(callback: CallbackQuery, session: AsyncSession) -> None:
    match = re.fullmatch(r"miswak:challenge:start:(7|30)", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    today = local_today(user.timezone)
    challenge, status = await miswak_repo.start_challenge(
        session, user.id, int(match[1]), today
    )
    await session.commit()
    if status == "inactive":
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    if challenge is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    _current, progress = await miswak_repo.challenge_state(session, user.id, today)
    await session.commit()
    await callback.answer("چالش شروع شد!" if status == "started" else "یک چالش فعال داری.")
    await show(
        callback,
        texts.miswak_challenge(challenge.duration, progress, challenge.ends_on.isoformat()),
        keyboards.miswak_challenge_kb(challenge.status == "active"),
    )


@router.callback_query(F.data == "miswak:challenge:cancel")
async def on_challenge_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    await miswak_repo.cancel_challenge(session, callback.from_user.id)
    await session.commit()
    await callback.answer("چالش لغو شد.")
    await render_miswak(callback, session, callback.from_user)


@router.callback_query(F.data == "miswak:league")
async def on_league(callback: CallbackQuery, session: AsyncSession) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    user, today = active
    profile = await miswak_repo.get_profile(session, user.id, today)
    rows = await miswak_repo.league_rows(session, today) if profile.league_opt_in else []
    await session.commit()
    await callback.answer()
    await show(
        callback,
        texts.miswak_league(rows, profile.league_opt_in),
        keyboards.miswak_league_kb(profile.league_opt_in),
    )


@router.callback_query(F.data == "miswak:league:toggle")
async def on_league_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    user, today = active
    profile = await miswak_repo.get_profile(session, user.id, today)
    if profile is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    enabled = not profile.league_opt_in
    if not await miswak_repo.toggle_league(session, user.id, enabled):
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    rows = await miswak_repo.league_rows(session, today) if enabled else []
    await session.commit()
    await callback.answer("عضویتت در لیگ فعال شد." if enabled else "از لیگ خارج شدی.")
    await show(
        callback,
        texts.miswak_league(rows, enabled),
        keyboards.miswak_league_kb(enabled),
    )


@router.callback_query(F.data == "miswak:buddies")
async def on_buddies(callback: CallbackQuery, session: AsyncSession) -> None:
    if await _active_user(session, callback.from_user) is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    rows = await miswak_repo.buddy_rows(session, callback.from_user.id)
    display_rows = [(pair_id, name) for pair_id, _user_id, name in rows]
    await session.commit()
    await callback.answer()
    await show(
        callback,
        texts.miswak_buddies(display_rows),
        keyboards.miswak_buddy_list_kb(display_rows),
    )


@router.callback_query(F.data == "miswak:buddy:invite")
async def on_buddy_invite(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if await _active_user(session, callback.from_user) is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    bot_user = await bot.get_me()
    if not bot_user.username:
        await callback.answer("لینک دعوت فعلاً در دسترس نیست.", show_alert=True)
        return
    token = new_invite_token()
    token_hash = invite_token_hash(token)
    if token_hash is None:
        await callback.answer("ساخت دعوت انجام نشد.", show_alert=True)
        return
    now = datetime.now(timezone.utc)
    created = await miswak_repo.create_buddy_invite(
        session, callback.from_user.id, token_hash, now + timedelta(days=7)
    )
    if not created:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    await session.commit()
    deep_link = f"https://t.me/{bot_user.username}?start={INVITE_PREFIX}{token}"
    share_url = "https://t.me/share/url?" + urlencode(
        {"url": deep_link, "text": "بیا رفیق مسباک بشیم 🤝"}, quote_via=quote
    )
    await callback.answer()
    await show(
        callback,
        texts.miswak_buddy_invite_ready(deep_link),
        keyboards.miswak_buddy_invite_kb(share_url),
    )


@router.callback_query(F.data.startswith("miswak:buddy:nudge:"))
async def on_buddy_nudge(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    match = re.fullmatch(r"miswak:buddy:nudge:(\d{1,10})", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.MISWAK_INACTIVE, show_alert=True)
        return
    user, today = active
    status, target_id = await miswak_repo.claim_buddy_nudge(
        session, user.id, int(match[1]), today
    )
    await session.commit()
    if status == "limit":
        await callback.answer("امروز برای این رفیق تلنگر فرستادی.", show_alert=True)
        return
    if status != "ok" or target_id is None:
        await callback.answer("این رفاقت فعال نیست.", show_alert=True)
        return
    try:
        await bot.send_message(target_id, texts.miswak_buddy_nudge(callback.from_user.full_name))
    except TelegramForbiddenError:
        await callback.answer("ارسال انجام نشد؛ رفیقت دسترسی ربات را بسته.", show_alert=True)
        return
    except TelegramAPIError:
        log.info("miswak buddy nudge failed from %s to %s", user.id, target_id)
        await callback.answer("ارسال تلنگر انجام نشد.", show_alert=True)
        return
    await callback.answer("تلنگر رفت 🔔")


@router.callback_query(F.data.startswith("miswak:buddy:end:"))
async def on_buddy_end(callback: CallbackQuery, session: AsyncSession) -> None:
    match = re.fullmatch(r"miswak:buddy:end:(\d{1,10})", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    ended = await miswak_repo.end_buddy_pair(
        session,
        callback.from_user.id,
        int(match[1]),
        datetime.now(timezone.utc),
    )
    await session.commit()
    await callback.answer("رفاقت پایان یافت." if ended else "رفاقت پیدا نشد.")
    rows = await miswak_repo.buddy_rows(session, callback.from_user.id)
    display_rows = [(pair_id, name) for pair_id, _user_id, name in rows]
    await show(
        callback,
        texts.miswak_buddies(display_rows),
        keyboards.miswak_buddy_list_kb(display_rows),
    )