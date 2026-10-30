from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class BookFlowNavigationMiddleware(BaseMiddleware):
    """Discard a book form when a different screen or command handles the update."""

    def __init__(self, form_states: frozenset[str]) -> None:
        self.form_states = form_states

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            data.get("raw_state") in self.form_states
            and not data["handler"].flags.get("book_form_input")
        ):
            await data["state"].clear()
        return await handler(event, data)
