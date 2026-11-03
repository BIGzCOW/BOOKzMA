import re
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers.common import show
from BOOKzMA.repositories import badges as badges_repo
from BOOKzMA.repositories import readings, streak_freezes, users
from BOOKzMA.repositories import mesbak as mesbak_repo
from BOOKzMA.repositories import support as support_repo
from BOOKzMA.services.mesbak import completed_days, current_streak
from BOOKzMA.services.streak import displayed_streak, longest_streak
from BOOKzMA.utils import local_today

router = Router()
SUPPORT_ACTION_RE = re.compile(r"support:(reply|block|continue):(\d{1,20})")
MAX_SUPPORT_TICKET_ID = 2_147_483_647


def _support_ticket_id(data: str | None, action: str) -> int | None:
    match = SUPPORT_ACTION_RE.fullmatch(data or "")
    if match is None or match[1] != action:
        return None
    ticket_id = int(match[2])
    return ticket_id if ticket_id <= MAX_SUPPORT_TICKET_ID else None


class SupportTicket(StatesGroup):
    waiting_for_message = State()


class SupportReply(StatesGroup):
    waiting_for_message = State()


SUPPORT_FORM_STATES = frozenset(
    state.state
    for state in (*SupportTicket.__all_states__, *SupportReply.__all_states__)
)


async def render_profile(event: Message | CallbackQuery, session: AsyncSession) -> None:
    tg = event.from_user if isinstance(event, Message) else event.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    today = local_today(user.timezone)
    mesbak_profile = await mesbak_repo.get_profile(session, user.id, today)
    mesbak_streak = None
    if mesbak_profile is not None and mesbak_profile.enabled:
        mesbak_streak = current_streak(
            completed_days(await mesbak_repo.daily_records(session, user.id)), today
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
            mesbak_streak,
        ),
        keyboards.profile_kb(
            user.leaderboard_opt_out, mesbak_profile is not None and mesbak_profile.enabled
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
    text = texts.streak_leaderboard(scores)
    current_user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    today = local_today(current_user.timezone)
    mesbak_profile = await mesbak_repo.get_profile(session, current_user.id, today)
    await session.commit()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.profile_kb(
                current_user.leaderboard_opt_out,
                mesbak_profile is not None and mesbak_profile.enabled,
            ),
        )


@router.callback_query(F.data == "support")
async def on_support_callback(
    callback: CallbackQuery, settings: Settings
) -> None:
    support_username = settings.support_telegram_username.strip().removeprefix("@")
    support_url = f"https://t.me/{support_username}" if re.fullmatch(
        r"[A-Za-z0-9_]{5,32}", support_username
    ) else ""
    github_url = settings.github_url.strip()
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", github_url):
        github_url = ""
    await callback.answer()
    await show(
        callback,
        texts.support(),
        keyboards.support_kb(github_url, support_url),
    )


@router.callback_query(
    F.data == "support:ticket",
    lambda callback: isinstance(callback.message, Message)
    and callback.message.chat.type == "private",
)
async def on_support_ticket(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    if await support_repo.is_blocked(session, user.id):
        await callback.answer(texts.SUPPORT_USER_BLOCKED, show_alert=True)
        return
    ticket = await support_repo.open_ticket(session, user.id)
    await session.commit()
    await state.clear()
    await state.set_data({"support_ticket_id": ticket.id})
    await state.set_state(SupportTicket.waiting_for_message)
    await callback.answer()
    await show(callback, texts.SUPPORT_ASK_MESSAGE, keyboards.support_cancel_kb())


@router.callback_query(
    F.data == "support:ticket",
    lambda callback: (
        not isinstance(callback.message, Message)
        or callback.message.chat.type != "private"
    ),
)
async def on_group_support_ticket(callback: CallbackQuery) -> None:
    await callback.answer(texts.BOOK_PRIVATE_ONLY, show_alert=True)


@router.callback_query(
    F.data.startswith("support:continue:"),
    lambda callback: isinstance(callback.message, Message)
    and callback.message.chat.type == "private",
)
async def on_support_continue(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    ticket_id = _support_ticket_id(callback.data, "continue")
    ticket = await support_repo.get_ticket(session, ticket_id) if ticket_id else None
    if ticket is None or ticket.user_id != callback.from_user.id or ticket.status != "open":
        await callback.answer(texts.SUPPORT_TICKET_MISSING, show_alert=True)
        return
    if await support_repo.is_blocked(session, ticket.user_id):
        await callback.answer(texts.SUPPORT_USER_BLOCKED, show_alert=True)
        return
    await state.clear()
    await state.set_data({"support_ticket_id": ticket.id})
    await state.set_state(SupportTicket.waiting_for_message)
    await callback.answer()
    await show(callback, texts.SUPPORT_ASK_MESSAGE, keyboards.support_cancel_kb())


@router.message(Command("support"))
@router.message(F.text == "💚 حمایت از پروژه")
@router.message(F.text == "💬 پشتیبانی")
@router.message(F.text == "💬 پشتیبانی / پیشنهاد")
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


@router.message(
    SupportTicket.waiting_for_message,
    F.chat.type == "private",
    flags={"book_form_input": True},
)
async def on_support_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    if not settings.admin_ids:
        await state.clear()
        await message.answer(texts.SUPPORT_NOT_CONFIGURED)
        return
    data = await state.get_data()
    ticket_id = data.get("support_ticket_id")
    ticket = (
        await support_repo.get_ticket(session, ticket_id)
        if isinstance(ticket_id, int)
        else None
    )
    if ticket is None or ticket.user_id != message.from_user.id or ticket.status != "open":
        await state.clear()
        await message.answer(texts.SUPPORT_TICKET_MISSING)
        return
    if await support_repo.is_blocked(session, ticket.user_id):
        await state.clear()
        await message.answer(texts.SUPPORT_USER_BLOCKED)
        return
    name = escape(message.from_user.full_name)
    delivered = False
    for admin_id in settings.admin_ids:
        try:
            copied = await message.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            delivered = True
            await message.bot.send_message(
                chat_id=admin_id,
                text=texts.SUPPORT_ADMIN_TICKET.format(
                    ticket_id=ticket.id, name=name, user_id=message.from_user.id
                ),
                reply_markup=keyboards.support_reply_kb(ticket.id, ticket.user_id, False),
                reply_to_message_id=copied.message_id,
            )
        except TelegramAPIError:
            continue

    if delivered:
        await support_repo.record_message(
            session, ticket.id, message.from_user.id, "user_message"
        )
        await session.commit()
    else:
        await session.rollback()
    await message.answer(
        texts.SUPPORT_RECEIVED if delivered else texts.SUPPORT_DELIVERY_FAILED,
        reply_markup=keyboards.support_user_reply_kb(ticket.id) if delivered else None,
    )


@router.callback_query(
    F.data.startswith("support:reply:"),
    lambda callback: isinstance(callback.message, Message)
    and callback.message.chat.type == "private",
)
async def on_support_reply(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer(texts.SUPPORT_REPLY_UNAUTHORIZED, show_alert=True)
        return
    ticket_id = _support_ticket_id(callback.data, "reply")
    ticket = await support_repo.get_ticket(session, ticket_id) if ticket_id else None
    if ticket is None or ticket.status != "open":
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await state.clear()
    await state.set_data({"support_ticket_id": ticket.id})
    await state.set_state(SupportReply.waiting_for_message)
    await callback.answer()
    await show(callback, texts.SUPPORT_ASK_REPLY, keyboards.support_cancel_kb())


@router.callback_query(
    F.data.startswith("support:block:"),
    lambda callback: isinstance(callback.message, Message)
    and callback.message.chat.type == "private",
)
async def on_support_block(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer(texts.SUPPORT_REPLY_UNAUTHORIZED, show_alert=True)
        return
    ticket_id = _support_ticket_id(callback.data, "block")
    ticket = await support_repo.get_ticket(session, ticket_id) if ticket_id else None
    if ticket is None:
        await callback.answer(texts.SUPPORT_TICKET_MISSING, show_alert=True)
        return
    blocked = await support_repo.toggle_block(
        session, ticket.user_id, callback.from_user.id
    )
    await session.commit()
    await callback.answer(texts.SUPPORT_BLOCKED if blocked else texts.SUPPORT_UNBLOCKED)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(
                reply_markup=keyboards.support_reply_kb(
                    ticket.id, ticket.user_id, blocked
                )
            )
        except TelegramAPIError:
            return


@router.message(
    SupportReply.waiting_for_message,
    F.chat.type == "private",
    flags={"book_form_input": True},
)
async def on_support_reply_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if message.from_user is None or message.from_user.id not in settings.admin_ids:
        await state.clear()
        return
    data = await state.get_data()
    ticket_id = data.get("support_ticket_id")
    ticket = (
        await support_repo.get_ticket(session, ticket_id)
        if isinstance(ticket_id, int)
        else None
    )
    if ticket is None or ticket.status != "open":
        await state.clear()
        await message.answer(texts.SUPPORT_TICKET_MISSING)
        return
    if message.text and message.text.startswith("/"):
        await state.clear()
        return
    try:
        await message.bot.copy_message(
            chat_id=ticket.user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=keyboards.support_user_reply_kb(ticket.id),
        )
    except TelegramAPIError:
        await message.answer(texts.SUPPORT_REPLY_FAILED)
        return
    await support_repo.record_message(
        session, ticket.id, message.from_user.id, "admin_reply"
    )
    await session.commit()
    await message.answer(texts.SUPPORT_REPLY_SENT)