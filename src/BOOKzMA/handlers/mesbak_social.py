import logging
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.handlers.common import show
from BOOKzMA.handlers.mesbak import render_mesbak
from BOOKzMA.db.models import User
from BOOKzMA.repositories import mesbak as mesbak_repo
from BOOKzMA.repositories import users
from BOOKzMA.services.mesbak_social import invite_token_hash, new_invite_token
from BOOKzMA.utils import local_today

router = Router()
log = logging.getLogger(__name__)
INVITE_PREFIX = "mesbakbuddy_"


async def _active_user(session: AsyncSession, tg_user) -> tuple[User, date] | None:
    user = await users.get_or_create(
        session, tg_user.id, tg_user.username, tg_user.full_name
    )
    today = local_today(user.timezone)
    profile = await mesbak_repo.get_profile(session, user.id, today)
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
    return await mesbak_repo.redeem_buddy_invite(
        session, token_hash, recipient_id, datetime.now(timezone.utc)
    )


async def _render_buddy_list(
    event: Message | CallbackQuery, session: AsyncSession, user_id: int
) -> None:
    rows = await mesbak_repo.buddy_rows(session, user_id)
    display_rows = [(pair_id, name) for pair_id, _user_id, name, _pair_type in rows]
    queued = await mesbak_repo.is_random_buddy_queued(session, user_id)
    await session.commit()
    await show(
        event,
        texts.mesbak_buddies(display_rows, queued),
        keyboards.mesbak_buddy_list_kb(display_rows, queued),
    )


@router.callback_query(F.data.startswith("mesbak:challenge:start:"))
async def on_challenge_start(callback: CallbackQuery, session: AsyncSession) -> None:
    match = re.fullmatch(r"mesbak:challenge:start:(7|30)", callback.data or "")
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
    challenge, status = await mesbak_repo.start_challenge(
        session, user.id, int(match[1]), today
    )
    await session.commit()
    if status == "inactive":
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    if challenge is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    _current, progress = await mesbak_repo.challenge_state(session, user.id, today)
    await session.commit()
    await callback.answer("چالش شروع شد!" if status == "started" else "یک چالش فعال داری.")
    await show(
        callback,
        texts.mesbak_challenge(challenge.duration, progress, challenge.ends_on.isoformat()),
        keyboards.mesbak_challenge_kb(challenge.status == "active"),
    )


@router.callback_query(F.data == "mesbak:challenge:cancel")
async def on_challenge_cancel(callback: CallbackQuery, session: AsyncSession) -> None:
    await mesbak_repo.cancel_challenge(session, callback.from_user.id)
    await session.commit()
    await callback.answer("چالش لغو شد.")
    await render_mesbak(callback, session, callback.from_user)


@router.callback_query(F.data == "mesbak:league")
async def on_league(callback: CallbackQuery, session: AsyncSession) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    user, today = active
    profile = await mesbak_repo.get_profile(session, user.id, today)
    rows = await mesbak_repo.league_rows(session, today) if profile.league_opt_in else []
    await session.commit()
    await callback.answer()
    await show(
        callback,
        texts.mesbak_league(rows, profile.league_opt_in),
        keyboards.mesbak_league_kb(profile.league_opt_in),
    )


@router.message(F.text == "🏆 لیگ مسباک")
async def on_league_menu(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    active = await _active_user(session, message.from_user)
    if active is None:
        await message.answer(texts.mesbak_INACTIVE)
        return
    user, today = active
    profile = await mesbak_repo.get_profile(session, user.id, today)
    rows = await mesbak_repo.league_rows(session, today) if profile.league_opt_in else []
    await session.commit()
    await message.answer(
        texts.mesbak_league(rows, profile.league_opt_in),
        reply_markup=keyboards.mesbak_league_kb(profile.league_opt_in),
    )


@router.callback_query(F.data == "mesbak:league:toggle")
async def on_league_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    user, today = active
    profile = await mesbak_repo.get_profile(session, user.id, today)
    if profile is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    enabled = not profile.league_opt_in
    if not await mesbak_repo.toggle_league(session, user.id, enabled):
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    rows = await mesbak_repo.league_rows(session, today) if enabled else []
    await session.commit()
    await callback.answer("عضویتت در لیگ فعال شد." if enabled else "از لیگ خارج شدی.")
    await show(
        callback,
        texts.mesbak_league(rows, enabled),
        keyboards.mesbak_league_kb(enabled),
    )


@router.callback_query(F.data == "mesbak:buddies")
async def on_buddies(callback: CallbackQuery, session: AsyncSession) -> None:
    if await _active_user(session, callback.from_user) is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    await callback.answer()
    await _render_buddy_list(callback, session, callback.from_user.id)


@router.message(F.text == "🤝 رفیق‌های مسباک")
async def on_buddies_menu(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    if await _active_user(session, message.from_user) is None:
        await message.answer(texts.mesbak_INACTIVE)
        return
    await _render_buddy_list(message, session, message.from_user.id)


@router.callback_query(F.data == "mesbak:buddy:random:join")
async def on_random_buddy_join(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.MESBAK_RANDOM_INACTIVE, show_alert=True)
        return
    user, _today = active
    status, partner_id = await mesbak_repo.join_random_buddy_queue(session, user.id)
    await session.commit()
    if status == "waiting":
        await callback.answer(texts.MESBAK_RANDOM_WAITING)
        await _render_buddy_list(callback, session, user.id)
        return
    if status != "matched" or partner_id is None:
        await callback.answer(texts.MESBAK_RANDOM_INACTIVE, show_alert=True)
        return
    partner = await session.get(User, partner_id)
    partner_name = texts.mesbak_buddy_name(partner.display_name if partner else None)
    if partner is not None:
        peer_text = texts.MESBAK_RANDOM_MATCHED_PEER.format(
            name=texts.mesbak_buddy_name(user.display_name)
        )
        try:
            await bot.send_message(partner_id, peer_text)
        except TelegramAPIError:
            log.info("anonymous Mesbak match notification to %s failed", partner_id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            texts.MESBAK_RANDOM_MATCHED_SELF.format(name=partner_name)
        )
    await _render_buddy_list(callback, session, user.id)


@router.callback_query(F.data == "mesbak:buddy:random:leave")
async def on_random_buddy_leave(callback: CallbackQuery, session: AsyncSession) -> None:
    await mesbak_repo.leave_random_buddy_queue(session, callback.from_user.id)
    await session.commit()
    await callback.answer(texts.MESBAK_RANDOM_LEFT_QUEUE)
    await _render_buddy_list(callback, session, callback.from_user.id)


@router.callback_query(F.data == "mesbak:buddy:invite")
async def on_buddy_invite(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if await _active_user(session, callback.from_user) is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
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
    created = await mesbak_repo.create_buddy_invite(
        session, callback.from_user.id, token_hash, now + timedelta(days=7)
    )
    if not created:
        queued = await mesbak_repo.is_random_buddy_queued(session, callback.from_user.id)
        message = texts.MESBAK_RANDOM_QUEUE_BUSY if queued else texts.mesbak_INACTIVE
        await callback.answer(message, show_alert=True)
        return
    await session.commit()
    deep_link = f"https://t.me/{bot_user.username}?start={INVITE_PREFIX}{token}"
    share_url = "https://t.me/share/url?" + urlencode(
        {"url": deep_link, "text": "بیا رفیق مسباک بشیم 🤝"}, quote_via=quote
    )
    await callback.answer()
    await show(
        callback,
        texts.mesbak_buddy_invite_ready(deep_link),
        keyboards.mesbak_buddy_invite_kb(share_url),
    )


@router.callback_query(F.data.startswith("mesbak:buddy:open:"))
async def on_buddy_open(callback: CallbackQuery, session: AsyncSession) -> None:
    match = re.fullmatch(r"mesbak:buddy:open:(\d{1,10})", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    if await _active_user(session, callback.from_user) is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    found = await mesbak_repo.buddy_pair_for_user(
        session, callback.from_user.id, int(match[1])
    )
    if found is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    pair, buddy = found
    today = local_today(buddy.timezone)
    completed = await mesbak_repo.completed_day_set(session, buddy.id)
    await session.commit()
    await callback.answer()
    await show(
        callback,
        texts.mesbak_buddy_screen(
            texts.mesbak_buddy_name(buddy.display_name), len(completed), today in completed
        ),
        keyboards.mesbak_buddy_pair_kb(pair.id),
    )


@router.callback_query(F.data == "mesbak:buddy:nudge:all")
async def on_buddy_nudge_all(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    user, today = active
    buddies = await mesbak_repo.buddy_users(session, user.id)
    completed = await mesbak_repo.users_completed_on_days(
        session, [(buddy.id, local_today(buddy.timezone)) for _pair, buddy in buddies]
    )
    ready: list[int] = []
    already_done = 0
    already_nudged = 0
    unavailable = 0
    for pair, buddy in buddies:
        if buddy.id in completed:
            already_done += 1
            continue
        status, target_id, _pair_type = await mesbak_repo.claim_buddy_nudge(
            session, user.id, pair.id, today
        )
        if status == "ok" and target_id is not None:
            ready.append(target_id)
        elif status == "limit":
            already_nudged += 1
        else:
            unavailable += 1
    await session.commit()
    await callback.answer()

    sent = 0
    failed = unavailable
    for target_id in ready:
        try:
            await bot.send_message(
                target_id, texts.mesbak_buddy_nudge(user.display_name)
            )
            sent += 1
        except TelegramAPIError:
            log.info("mesbak bulk nudge to %s failed", target_id)
            failed += 1

    if isinstance(callback.message, Message):
        summary = texts.mesbak_buddy_nudge_summary(sent, already_done, already_nudged, failed)
        if callback.message.text == texts.MESBAK_BUDDY_NUDGE_PROMPT:
            try:
                await callback.message.edit_text(summary)
            except TelegramAPIError:
                await callback.message.answer(summary)
        else:
            await callback.message.answer(summary)


@router.callback_query(F.data == "mesbak:buddy:nudge:dismiss")
async def on_dismiss_buddy_nudge(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message) or (
        callback.message.text != texts.MESBAK_BUDDY_NUDGE_PROMPT
    ):
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    await show(callback, texts.MESBAK_BUDDY_NUDGE_DISMISSED, None)


@router.callback_query(F.data.startswith("mesbak:buddy:nudge:"))
async def on_buddy_nudge(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    match = re.fullmatch(r"mesbak:buddy:nudge:(\d{1,10})", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    active = await _active_user(session, callback.from_user)
    if active is None:
        await callback.answer(texts.mesbak_INACTIVE, show_alert=True)
        return
    user, today = active
    status, target_id, _pair_type = await mesbak_repo.claim_buddy_nudge(
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
        await bot.send_message(
            target_id, texts.mesbak_buddy_nudge(user.display_name)
        )
    except TelegramForbiddenError:
        await callback.answer("ارسال انجام نشد؛ رفیقت دسترسی ربات را بسته.", show_alert=True)
        return
    except TelegramAPIError:
        log.info("mesbak buddy nudge failed from %s to %s", user.id, target_id)
        await callback.answer("ارسال تلنگر انجام نشد.", show_alert=True)
        return
    await callback.answer("تلنگر رفت 🔔")


@router.callback_query(F.data.startswith("mesbak:buddy:end:"))
async def on_buddy_end(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    match = re.fullmatch(r"mesbak:buddy:end:(\d{1,10})", callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    partner_id = await mesbak_repo.end_buddy_pair(
        session,
        callback.from_user.id,
        int(match[1]),
        datetime.now(timezone.utc),
    )
    await session.commit()
    if partner_id is not None:
        try:
            await bot.send_message(partner_id, texts.MESBAK_BUDDY_ENDED)
        except TelegramAPIError:
            log.info("mesbak buddy end notification to %s failed", partner_id)
    await callback.answer(texts.MESBAK_BUDDY_ENDED if partner_id else "رفاقت پیدا نشد.")
    await _render_buddy_list(callback, session, callback.from_user.id)
