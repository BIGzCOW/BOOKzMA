from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.constants import TIMEZONES, TZ_LABELS
from BOOKzMA.handlers.common import render_home, show
from BOOKzMA.repositories import users

router = Router()


async def render_timezone(
    event: Message | CallbackQuery, session: AsyncSession, tg: TgUser
) -> None:
    user = await users.get_or_create(session, tg.id, tg.username)
    await session.commit()
    label = TZ_LABELS.get(user.timezone, user.timezone)
    await show(event, texts.timezone(label), keyboards.timezone_kb())


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if message.from_user:
        await render_timezone(message, session, message.from_user)


@router.message(F.text == "🌍 منطقه زمانی")
async def on_menu_timezone(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await cmd_timezone(message, session, state)


@router.callback_query(F.data == "tz")
async def on_timezone(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await render_timezone(callback, session, callback.from_user)


@router.callback_query(F.data.startswith("tz_set:"))
async def on_timezone_set(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    raw = (callback.data or "").split(":", 1)[1]
    if not raw.isdigit() or int(raw) >= len(TIMEZONES):
        await callback.answer()
        return
    label, tz_name = TIMEZONES[int(raw)]
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username)
    await users.set_timezone(session, user.id, tz_name)
    await session.commit()
    await callback.answer(f"منطقه زمانی: {label}")
    await render_home(callback, session, tg)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            texts.MAIN_MENU_HINT,
            reply_markup=keyboards.menu_kb(tg.id in settings.admin_ids),
        )
