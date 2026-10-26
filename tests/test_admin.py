import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import Chat, InlineKeyboardMarkup, Message
from aiogram.types import CallbackQuery, User
from pydantic import SecretStr

from BOOKzMA.config import Settings
from BOOKzMA.handlers.admin import (
    _campaign_id,
    _valid_broadcast_url,
    is_admin,
    on_admin_stats,
)
from BOOKzMA.handlers.common import show
from BOOKzMA.middlewares.membership import MembershipMiddleware


def test_admin_authorization_uses_configured_allowlist():
    settings = Settings(bot_token=SecretStr("test"), admin_telegram_ids="123,456")

    assert is_admin(123, settings)
    assert not is_admin(789, settings)


def test_campaign_callback_ids_are_strictly_parsed():
    assert _campaign_id("broadcast:start:42", "start") == 42
    assert _campaign_id("broadcast:start:-1", "start") is None
    assert _campaign_id("broadcast:start:12345678901", "start") is None
    assert _campaign_id("broadcast:start:2147483648", "start") is None
    assert _campaign_id("broadcast:start:42:extra", "start") is None
    assert _campaign_id("broadcast:cancel:42", "start") is None


def test_broadcast_button_url_requires_valid_https_without_userinfo():
    assert _valid_broadcast_url("https://example.com/lesson")
    assert not _valid_broadcast_url("http://example.com/lesson")
    assert not _valid_broadcast_url("https://user:secret@example.com/lesson")
    assert not _valid_broadcast_url("https://[broken")
    assert not _valid_broadcast_url("https://example.com:invalid")


def test_configured_admin_bypasses_membership_middleware(monkeypatch):
    async def fail_membership_check(_bot, _user_id):
        raise AssertionError("admin should bypass the membership check")

    async def run_test():
        from_user = User(id=123, is_bot=False, first_name="Admin")
        callback = CallbackQuery(
            id="callback",
            from_user=from_user,
            chat_instance="chat",
            data="admin:stats",
        )
        called = False

        async def handler(_event, _data):
            nonlocal called
            called = True
            return "handled"

        monkeypatch.setattr(
            "BOOKzMA.middlewares.membership.missing_channels", fail_membership_check
        )
        middleware = MembershipMiddleware(frozenset({123}))
        result = await middleware(
            handler,
            callback,
            {"event_from_user": from_user, "bot": object()},
        )
        assert result == "handled"
        assert called

    asyncio.run(run_test())


def test_non_admin_cannot_call_admin_stats_callback():
    async def run_test():
        answers = []

        async def answer(text, show_alert=False):
            answers.append((text, show_alert))

        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=789),
            answer=answer,
        )
        settings = Settings(bot_token=SecretStr("test"), admin_telegram_ids="123")

        await on_admin_stats(callback, None, settings)

        assert answers == [("دسترسی نداری.", True)]

    asyncio.run(run_test())


def test_show_ignores_unchanged_telegram_message(monkeypatch):
    async def reject_unchanged(self, *_args, **_kwargs):
        raise TelegramBadRequest(
            method=EditMessageText(chat_id=1, message_id=1, text="same"),
            message="Bad Request: message is not modified",
        )

    monkeypatch.setattr(Message, "edit_text", reject_unchanged)
    message = Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type="private"),
        text="same",
    )
    callback = CallbackQuery(
        id="callback",
        from_user=User(id=123, is_bot=False, first_name="Admin"),
        chat_instance="chat",
        message=message,
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[])

    asyncio.run(show(callback, "same", markup))