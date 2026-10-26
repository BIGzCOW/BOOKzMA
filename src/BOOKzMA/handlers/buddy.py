"""رفیق مطالعه (C-06): opt-in، صف خودکار FIFO، تلنگر روزانه و پایان بدون سرزنش."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.db.models import User
from BOOKzMA.handlers.common import show
from BOOKzMA.repositories import buddy as buddy_repo
from BOOKzMA.repositories import readings, users
from BOOKzMA.repositories import streak_freezes
from BOOKzMA.services.streak import displayed_streak
from BOOKzMA.services.buddy_invites import create_invite_token
from BOOKzMA.services.buddy_nudges import classify_nudge_targets
from BOOKzMA.utils import local_today

router = Router()
log = logging.getLogger(__name__)


async def render_buddy(event: Message | CallbackQuery, session: AsyncSession, tg: TgUser) -> None:
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    await session.commit()
    buddies = await buddy_repo.active_buddy_users(session, user.id)
    queued = await buddy_repo.is_queued(session, user.id)
    if buddies or queued:
        body = texts.buddy_overview([buddy.display_name for _pair, buddy in buddies], queued)
        if queued and not buddies:
            body = texts.BUDDY_WAITING
        await show(
            event,
            body,
            keyboards.buddy_list_kb(
                [(pair.id, texts.buddy_button_name(buddy.display_name)) for pair, buddy in buddies],
                queued,
            ),
        )
        return
    await show(event, texts.BUDDY_INTRO, keyboards.buddy_intro_kb())


async def _show_pair(
    event: Message | CallbackQuery, session: AsyncSession, tg: TgUser, pair_id: int
) -> bool:
    found = await buddy_repo.active_pair_for_user(session, tg.id, pair_id)
    if found is None:
        return False
    pair, buddy_id = found
    buddy = await session.get(User, buddy_id)
    if buddy is None:
        return False
    today = local_today(buddy.timezone)
    buddy_read_today = await readings.has_read(session, buddy.id, today)
    buddy_days = await readings.get_days(session, buddy.id)
    buddy_frozen = await streak_freezes.used_days(session, buddy.id)
    streak = displayed_streak(
        buddy_days,
        today,
        buddy_frozen,
        buddy.comeback_bonus_days,
        buddy.comeback_base_day,
    )
    await show(
        event,
        texts.buddy_screen(texts.buddy_name(buddy.display_name), streak, buddy_read_today),
        keyboards.buddy_pair_kb(pair.id),
    )
    return True


def _callback_pair_id(data: str | None, prefix: str) -> int | None:
    if data is None or not data.startswith(prefix):
        return None
    raw_id = data.removeprefix(prefix)
    if not raw_id.isascii() or not raw_id.isdigit():
        return None
    if len(raw_id) > 10:
        return None
    pair_id = int(raw_id)
    return pair_id if 0 < pair_id <= 2_147_483_647 else None


async def _safe_send(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
    except TelegramAPIError:
        log.info("buddy notification to %s failed", user_id)
        return False
    return True


@router.message(F.text == "🤝 رفیق مطالعه")
async def on_menu_buddy(message: Message, session: AsyncSession) -> None:
    if message.from_user:
        await render_buddy(message, session, message.from_user)


@router.callback_query(F.data == "buddy:list")
async def on_buddy_list(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await render_buddy(callback, session, callback.from_user)


@router.callback_query(F.data.startswith("buddy:open:"))
async def on_open_pair(callback: CallbackQuery, session: AsyncSession) -> None:
    pair_id = _callback_pair_id(callback.data, "buddy:open:")
    if pair_id is None or not await _show_pair(callback, session, callback.from_user, pair_id):
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "buddy:invite")
async def on_invite(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    bot_user = await bot.get_me()
    if not bot_user.username:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return

    payload, token_hash = create_invite_token()
    now = datetime.now(timezone.utc)
    created = await buddy_repo.create_invite(
        session, user.id, token_hash, now + timedelta(days=7)
    )
    await session.commit()
    if not created:
        await callback.answer(texts.BUDDY_ALREADY_QUEUED, show_alert=True)
        return

    await callback.answer()
    if isinstance(callback.message, Message):
        deep_link = f"https://t.me/{bot_user.username}?start={payload}"
        await callback.message.answer(
            texts.BUDDY_INVITE_READY.format(link=deep_link),
            reply_markup=keyboards.buddy_invite_kb(deep_link),
        )


@router.callback_query(F.data == "buddy:nudge:all")
async def on_nudge_all(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    buddies = await buddy_repo.active_buddy_users(session, user.id)
    nudge_day = local_today(user.timezone)
    read_user_ids = await readings.users_read_on_days(
        session,
        [(buddy.id, local_today(buddy.timezone)) for _pair, buddy in buddies],
    )
    targets, already_read, already_nudged = classify_nudge_targets(
        buddies, read_user_ids, nudge_day
    )

    ready = []
    for pair, buddy in targets:
        if await buddy_repo.register_nudge(session, pair, nudge_day):
            ready.append((pair, buddy))
        else:
            already_nudged += 1
    await session.commit()
    await callback.answer()

    sent = 0
    failed = 0
    for _pair, buddy in ready:
        delivered = await _safe_send(
            bot, buddy.id, texts.NUDGE_PUSH.format(name=texts.buddy_name(user.display_name))
        )
        sent += int(delivered)
        failed += int(not delivered)

    summary = texts.buddy_nudge_summary(sent, already_read, already_nudged, failed)
    if isinstance(callback.message, Message):
        await callback.message.answer(summary)


@router.callback_query(F.data == "buddy:nudge:dismiss")
async def on_dismiss_nudge_prompt(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "buddy:join")
async def on_join(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, state: FSMContext
) -> None:
    await state.clear()
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    joined = await buddy_repo.join_queue(session, user.id)
    partner_id = await buddy_repo.try_match(session, user.id) if joined else None
    await session.commit()
    if not joined:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        await render_buddy(callback, session, tg)
        return
    my_name = texts.buddy_name(user.display_name)
    if partner_id is None:
        await callback.answer()
        await render_buddy(callback, session, tg)
        return
    partner = await session.get(User, partner_id)
    partner_name = texts.buddy_name(partner.display_name if partner else None)
    if partner is not None:
        await _safe_send(bot, partner.id, texts.BUDDY_MATCHED_PEER.format(name=my_name))
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(texts.BUDDY_MATCHED_SELF.format(name=partner_name))
        await render_buddy(callback.message, session, tg)


@router.callback_query(F.data == "buddy:leave")
async def on_leave(callback: CallbackQuery, session: AsyncSession) -> None:
    await buddy_repo.leave_queue(session, callback.from_user.id)
    await session.commit()
    await callback.answer(texts.BUDDY_LEFT_QUEUE)
    await render_buddy(callback, session, callback.from_user)


@router.callback_query(F.data.startswith("buddy:nudge:"))
async def on_nudge(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    pair_id = _callback_pair_id(callback.data, "buddy:nudge:")
    if pair_id is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username)
    found = await buddy_repo.active_pair_for_user(session, user.id, pair_id)
    if found is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    pair, buddy_id = found
    buddy = await session.get(User, buddy_id)
    if buddy is not None and await readings.has_read(
        session, buddy.id, local_today(buddy.timezone)
    ):
        await callback.answer(texts.BUDDY_ALREADY_READ)
        return
    today = local_today(user.timezone)
    allowed = await buddy_repo.register_nudge(session, pair, today)
    await session.commit()
    if not allowed:
        await callback.answer(texts.BUDDY_NUDGE_LIMIT)
        return
    delivered = await _safe_send(
        bot, buddy_id, texts.NUDGE_PUSH.format(name=texts.buddy_name(user.display_name))
    )
    await callback.answer(texts.BUDDY_NUDGE_SENT if delivered else texts.INVALID_ACTION)


@router.callback_query(F.data.startswith("buddy:end:"))
async def on_end(
    callback: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    pair_id = _callback_pair_id(callback.data, "buddy:end:")
    if pair_id is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    found = await buddy_repo.active_pair_for_user(session, user.id, pair_id)
    if found is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    pair, buddy_id = found
    await buddy_repo.end_pair(session, pair, user.id)
    await session.commit()
    await _safe_send(bot, buddy_id, texts.BUDDY_ENDED)
    await callback.answer(texts.BUDDY_ENDED)
    await render_buddy(callback, session, tg)
