import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.constants import REQUIRED_CHANNELS
from BOOKzMA.repositories import activity, users

log = logging.getLogger(__name__)

MEMBER_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}
CACHE_SECONDS = 300


async def missing_channels(bot: Bot, user_id: int) -> list[str]:
    """کانال‌هایی که کاربر عضوشون نیست. اگه چک خطا بده عضو حساب نمی‌شه."""
    missing = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in MEMBER_STATUSES:
                missing.append(channel)
        except TelegramAPIError:
            log.exception("membership check failed for %s (is the bot an admin there?)", channel)
            missing.append(channel)
    return missing


class MembershipMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: frozenset[int] = frozenset()) -> None:
        self._ok_until: dict[int, float] = {}
        self.admin_ids = admin_ids

    async def _record_activity(self, event: TelegramObject, data: dict[str, Any]) -> None:
        tg_user = data.get("event_from_user")
        session = data.get("session")
        if tg_user is None or not isinstance(session, AsyncSession):
            return
        user = await users.get_or_create(
            session, tg_user.id, tg_user.username, tg_user.full_name
        )
        await activity.record_interaction(session, user.id, datetime.now(timezone.utc).date())
        await session.commit()

    async def _record_start(self, event: Message, data: dict[str, Any]) -> None:
        tg_user = event.from_user
        session = data.get("session")
        if tg_user is None or not isinstance(session, AsyncSession):
            return
        user = await users.get_or_create(
            session, tg_user.id, tg_user.username, tg_user.full_name
        )
        await users.mark_started(session, user.id)
        await session.commit()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = getattr(event, "chat", None)
        if chat is None and isinstance(event, CallbackQuery):
            chat = getattr(getattr(event, "message", None), "chat", None)
        if getattr(chat, "is_direct_messages", False):
            return None
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "account_restore":
            return await handler(event, data)
        session = data.get("session")
        if isinstance(session, AsyncSession) and await users.is_deleted(session, user.id):
            if isinstance(event, CallbackQuery):
                await event.answer()
                if isinstance(event.message, Message):
                    await event.message.answer(
                        texts.ACCOUNT_DELETED_NOTICE, reply_markup=keyboards.restore_kb()
                    )
            elif isinstance(event, Message):
                await event.answer(
                    texts.ACCOUNT_DELETED_NOTICE, reply_markup=keyboards.restore_kb()
                )
            return None
        if isinstance(event, Message) and event.text:
            command = event.text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
            if command == "/start":
                await self._record_start(event, data)
        if isinstance(event, CallbackQuery) and event.data == "check_join":
            return await handler(event, data)
        if user.id in self.admin_ids:
            await self._record_activity(event, data)
            return await handler(event, data)
        if self._ok_until.get(user.id, 0) > time.monotonic():
            await self._record_activity(event, data)
            return await handler(event, data)

        bot: Bot = data["bot"]
        missing = await missing_channels(bot, user.id)
        if not missing:
            self._ok_until[user.id] = time.monotonic() + CACHE_SECONDS
            await self._record_activity(event, data)
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            try:
                await event.answer(texts.JOIN_FIRST, show_alert=True)
            except TelegramBadRequest as exc:
                log.warning("join-gate callback answer failed: %s", exc)
                return None
            if isinstance(event.message, Message):
                try:
                    await event.message.answer(
                        texts.JOIN_GATE, reply_markup=keyboards.join_kb(missing)
                    )
                except TelegramBadRequest as exc:
                    log.warning("join-gate message answer failed: %s", exc)
        elif isinstance(event, Message):
            try:
                await event.answer(texts.JOIN_GATE, reply_markup=keyboards.join_kb(missing))
            except TelegramBadRequest as exc:
                log.warning("join-gate answer failed: %s", str(exc).replace("\n", " "))
        return None
