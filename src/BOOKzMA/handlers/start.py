from datetime import date, datetime, timezone
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers.common import render_home
from BOOKzMA.handlers.onboarding import start_onboarding
from BOOKzMA.handlers.mesbak_social import (
    INVITE_PREFIX as MESBAK_INVITE_PREFIX,
    redeem_start_invite,
)
from BOOKzMA.middlewares.membership import missing_channels
from BOOKzMA.db.models import User
from BOOKzMA.repositories import buddy as buddy_repo
from BOOKzMA.repositories import activity, readings, users
from BOOKzMA.services.buddy_invites import INVITE_PREFIX, invite_token_hash
from BOOKzMA.utils import local_today

router = Router()
log = logging.getLogger(__name__)

WELCOME_BACK_AFTER_DAYS = 7


def is_returning_reader(last_read: date | None, today: date) -> bool:
    """کاربر قبلاً مطالعه داشته ولی بیش از یک هفته غیبت کرده."""
    return last_read is not None and (today - last_read).days > WELCOME_BACK_AFTER_DAYS


async def _accept_buddy_invite(
    message: Message, session: AsyncSession, bot: Bot, payload: str, user: User
) -> None:
    token_hash = invite_token_hash(payload)
    if token_hash is None:
        await message.answer(texts.BUDDY_INVITE_UNAVAILABLE)
        return

    status, inviter_id = await buddy_repo.redeem_invite(
        session, token_hash, user.id, datetime.now(timezone.utc)
    )
    await session.commit()
    if status == "busy":
        await message.answer(texts.BUDDY_INVITE_BUSY)
        return
    if status == "already":
        await message.answer(texts.BUDDY_INVITE_ALREADY_FRIENDS)
        return
    if status != "accepted" or inviter_id is None:
        await message.answer(texts.BUDDY_INVITE_UNAVAILABLE)
        return

    inviter = await session.get(User, inviter_id)
    inviter_name = texts.buddy_name(inviter.display_name if inviter else None)
    recipient_name = texts.buddy_name(user.display_name)
    try:
        await bot.send_message(
            inviter_id, texts.BUDDY_INVITE_PEER_ACCEPTED.format(name=recipient_name)
        )
    except TelegramAPIError:
        log.info("buddy invite notification to %s failed", inviter_id)
    await message.answer(texts.BUDDY_INVITE_ACCEPTED.format(name=inviter_name))


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings,
    command: CommandObject | None = None,
    bot: Bot | None = None,
) -> None:
    await state.clear()
    if message.from_user:
        tg = message.from_user
        user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
        await session.commit()
        if command and command.args:
            if bot is not None and command.args.startswith(INVITE_PREFIX):
                await _accept_buddy_invite(message, session, bot, command.args, user)
            elif command.args.startswith(MESBAK_INVITE_PREFIX):
                status, inviter_id = await redeem_start_invite(session, user.id, command.args)
                await session.commit()
                if status == "inactive":
                    await message.answer(
                        texts.mesbak_BUDDY_INACTIVE,
                        reply_markup=keyboards.mesbak_intro_kb(),
                    )
                elif status == "accepted":
                    await message.answer(texts.mesbak_BUDDY_ACCEPTED)
                    if bot is not None and inviter_id is not None:
                        try:
                            await bot.send_message(inviter_id, texts.mesbak_BUDDY_ACCEPTED)
                        except TelegramAPIError:
                            log.info("mesbak buddy invite notification failed")
                elif status == "already":
                    await message.answer(texts.mesbak_BUDDY_ALREADY)
                elif status == "self":
                    await message.answer(texts.mesbak_BUDDY_SELF)
                else:
                    await message.answer(texts.mesbak_BUDDY_UNAVAILABLE)
        if user.onboarded_at is None:
            await start_onboarding(message, session, state)
            return
        today = local_today(user.timezone)
        if is_returning_reader(await readings.last_read_day(session, user.id), today):
            await message.answer(texts.WELCOME_BACK)
        await render_home(message, session, tg)
        await message.answer(
            "از منوی پایین استفاده کن.",
            reply_markup=keyboards.menu_kb(tg.id in settings.admin_ids),
        )

@router.callback_query(F.data == "home")
async def on_home(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await render_home(callback, session, callback.from_user)


@router.message(F.text == "🏠 خانه")
async def on_menu_home(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    if message.from_user:
        await render_home(message, session, message.from_user)


@router.callback_query(F.data == "check_join")
async def on_check_join(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext
) -> None:
    missing = await missing_channels(bot, callback.from_user.id)
    if missing:
        await callback.answer(texts.NOT_JOINED, show_alert=True)
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(
                    texts.JOIN_GATE, reply_markup=keyboards.join_kb(missing)
                )
            except TelegramBadRequest:
                pass
        return
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    await activity.record_interaction(session, user.id, datetime.now(timezone.utc).date())
    if user.onboarded_at is None:
        await callback.answer(texts.JOINED)
        if isinstance(callback.message, Message):
            await start_onboarding(callback.message, session, state)
            return
        await render_home(callback, session, callback.from_user)
        return
    await callback.answer(texts.JOINED)
    await render_home(callback, session, callback.from_user)
