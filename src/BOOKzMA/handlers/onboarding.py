"""فلوی آنبردینگ کوتاه کاربر جدید (U-01): یک مرحله، انتخاب اولین یادآور."""

from datetime import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.constants import PRESET_TIMES
from BOOKzMA.handlers.common import render_home
from BOOKzMA.repositories import reminders as reminders_repo
from BOOKzMA.repositories import users

router = Router()

PRESET_SECONDS = {t.replace(":", "") for t in PRESET_TIMES}


async def start_onboarding(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.ONBOARDING_WELCOME, reply_markup=keyboards.onboarding_time_kb())


async def _finish(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    toast: str,
    settings: Settings,
) -> None:
    await users.mark_onboarded(session, callback.from_user.id)
    await session.commit()
    await state.clear()
    await callback.answer(toast)
    await render_home(callback, session, callback.from_user)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "از منوی پایین استفاده کن.",
            reply_markup=keyboards.menu_kb(callback.from_user.id in settings.admin_ids),
        )


@router.callback_query(F.data == "onb:skip")
async def on_skip(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, settings: Settings
) -> None:
    await _finish(callback, session, state, texts.ONBOARDING_SKIPPED, settings)


@router.callback_query(F.data.startswith("onb:"))
async def on_pick_time(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, settings: Settings
) -> None:
    raw = (callback.data or "").removeprefix("onb:")
    if raw not in PRESET_SECONDS:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    tg: TgUser = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username)
    result = await reminders_repo.add(session, user.id, time(int(raw[:2]), int(raw[2:])))
    toast = texts.ADD_RESULT[result] if result != "ok" else texts.ONBOARDING_DONE
    await _finish(callback, session, state, toast, settings)
