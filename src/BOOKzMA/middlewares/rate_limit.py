import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from BOOKzMA import texts

log = logging.getLogger(__name__)

# سقف تعداد کاربران ردیابی‌شده؛ بعد از رسیدن به آن، ورودی‌های منقضی پاک می‌شوند.
TRACKED_LIMIT = 1024


class RateLimitMiddleware(BaseMiddleware):
    """سقف ساده روی تعداد آپدیت هر کاربر در یک پنجرهٔ زمانی.

    حافظهٔ per-process است و به تصمیم D-04 (تک‌پروسس بودن اپلیکیشن) تکیه دارد.
    آپدیتِ مسدودشده به هندلر نمی‌رسد و هشدار هم حداکثر یک بار در هر پنجره
    فرستاده می‌شود تا خود ربات پیام اضافه تولید نکند.
    """

    def __init__(
        self,
        max_updates: int,
        window_seconds: int,
        admin_ids: frozenset[int] = frozenset(),
    ) -> None:
        self.max_updates = max(1, int(max_updates))
        self.window_seconds = max(1, int(window_seconds))
        self.admin_ids = admin_ids
        self._hits: dict[int, list[float]] = {}
        self._warned_until: dict[int, float] = {}

    def _cleanup(self, now: float) -> None:
        window_start = now - self.window_seconds
        stale = [
            user_id
            for user_id, hits in self._hits.items()
            if hits[-1] <= window_start and self._warned_until.get(user_id, 0) <= now
        ]
        for user_id in stale:
            self._hits.pop(user_id, None)
            self._warned_until.pop(user_id, None)

    async def _warn(self, event: TelegramObject, data: dict[str, Any]) -> None:
        if isinstance(event, CallbackQuery):
            try:
                await event.answer(texts.RATE_LIMITED)
            except Exception:
                log.debug("rate-limit callback answer failed", exc_info=True)
        elif isinstance(event, Message):
            try:
                await event.answer(texts.RATE_LIMITED)
            except Exception:
                log.debug("rate-limit message answer failed", exc_info=True)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id in self.admin_ids:
            return await handler(event, data)

        now = time.monotonic()
        if len(self._hits) >= TRACKED_LIMIT:
            self._cleanup(now)

        window_start = now - self.window_seconds
        hits = [hit for hit in self._hits.get(user.id, []) if hit > window_start]
        if len(hits) >= self.max_updates:
            self._hits[user.id] = hits
            log.warning(
                "rate limit exceeded user_id=%s window_seconds=%s limit=%s",
                user.id,
                self.window_seconds,
                self.max_updates,
            )
            if self._warned_until.get(user.id, 0) <= now:
                self._warned_until[user.id] = now + self.window_seconds
                await self._warn(event, data)
            return None

        hits.append(now)
        self._hits[user.id] = hits
        return await handler(event, data)
