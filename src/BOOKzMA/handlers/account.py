"""فلوی حذف کامل حساب کاربر: چهار گام با سه روش تأیید مختلف (N-04)."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.constants import DELETE_CONFIRM_WORD, DELETE_REASONS
from BOOKzMA.handlers.common import render_home, show
from BOOKzMA.handlers.profile import render_profile
from BOOKzMA.repositories import users

router = Router()


class DeleteAccount(StatesGroup):
    waiting_word = State()


@router.message(F.text == "🗑 حذف حساب")
async def on_delete_start_from_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        texts.ACCOUNT_DELETE_WARN, reply_markup=keyboards.account_delete_warn_kb()
    )


def _normalize(text: str) -> str:
    return text.replace("\u200c", " ").strip()


@router.callback_query(F.data == "account_del:start")
async def on_delete_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, texts.ACCOUNT_DELETE_WARN, keyboards.account_delete_warn_kb())


@router.callback_query(F.data == "account_del:why")
async def on_delete_why(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await show(callback, texts.ACCOUNT_DELETE_WHY, keyboards.account_delete_reasons_kb())


@router.callback_query(F.data.startswith("account_del:reason:"))
async def on_delete_reason(callback: CallbackQuery, state: FSMContext) -> None:
    index = callback.data.removeprefix("account_del:reason:")
    if not index.isdecimal() or int(index) >= len(DELETE_REASONS):
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await state.set_state(DeleteAccount.waiting_word)
    await state.update_data(reason=DELETE_REASONS[int(index)][0])
    await callback.answer()
    await show(callback, texts.ACCOUNT_DELETE_TYPE, keyboards.account_delete_type_kb())


@router.message(DeleteAccount.waiting_word, F.text)
async def on_delete_word(message: Message, state: FSMContext) -> None:
    if _normalize(message.text) != DELETE_CONFIRM_WORD:
        await message.answer(texts.ACCOUNT_DELETE_BAD_WORD)
        return
    await state.set_state(None)
    await message.answer(
        texts.ACCOUNT_DELETE_FINAL, reply_markup=keyboards.account_delete_final_kb()
    )


@router.message(DeleteAccount.waiting_word)
async def on_delete_word_not_text(message: Message) -> None:
    await message.answer(texts.ACCOUNT_DELETE_BAD_WORD)


@router.callback_query(F.data == "account_del:go")
async def on_delete_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    await state.clear()
    await users.delete_account(session, callback.from_user.id, data.get("reason"))
    await session.commit()
    await callback.answer()
    await show(callback, texts.ACCOUNT_DELETED_DONE, None)


@router.callback_query(F.data == "account_del:cancel")
async def on_delete_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    await callback.answer(texts.ACCOUNT_DELETE_CANCELLED)
    await render_profile(callback, session)


@router.callback_query(F.data == "account_restore")
async def on_account_restore(callback: CallbackQuery, session: AsyncSession) -> None:
    await users.restore_account(session, callback.from_user.id)
    await session.commit()
    await callback.answer(texts.ACCOUNT_RESTORED)
    await render_home(callback, session, callback.from_user)
