import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Chat, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import texts
from BOOKzMA.handlers.account import DeleteAccount, _normalize, on_delete_confirm, on_delete_reason
from BOOKzMA.handlers.account import on_account_restore, on_delete_word, on_delete_word_not_text
from BOOKzMA.middlewares.membership import MembershipMiddleware
from BOOKzMA.repositories import users


def _callback(data: str, user_id: int = 777) -> tuple[SimpleNamespace, list]:
    """هندلرها به isinstance کلاس‌های تلگرام وابسته نیستند؛ نمونهٔ سبک کافی است."""
    answers = []

    async def answer(text=None, show_alert=False):
        answers.append((text, show_alert))

    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id), data=data, answer=answer, message=None
    ), answers


def _state(data: dict | None = None) -> tuple[SimpleNamespace, dict]:
    recorded = {"states": [], "updates": [], "clears": 0}

    async def set_state(state) -> None:
        recorded["states"].append(state)

    async def update_data(**kwargs) -> None:
        recorded["updates"].append(kwargs)

    async def get_data() -> dict:
        return dict(data or {})

    async def clear() -> None:
        recorded["clears"] += 1

    return SimpleNamespace(
        set_state=set_state, update_data=update_data, get_data=get_data, clear=clear
    ), recorded


def test_normalize_strips_zwnj_and_whitespace():
    assert _normalize(" حذف ") == "حذف"
    assert _normalize("حذف\u200c") == "حذف"
    assert _normalize("حذف حساب") == "حذف حساب"


def test_reason_callback_rejects_out_of_range_index():
    async def run_test():
        callback, answers = _callback("account_del:reason:99")
        state, recorded = _state()
        await on_delete_reason(callback, state)

        assert answers == [(texts.INVALID_ACTION, True)]
        assert recorded["states"] == []

    asyncio.run(run_test())


def test_reason_callback_accepts_known_index_and_asks_typed_word():
    async def run_test():
        callback, _answers = _callback("account_del:reason:1")
        state, recorded = _state()
        await on_delete_reason(callback, state)

        assert recorded["states"] == [DeleteAccount.waiting_word]
        assert recorded["updates"] == [{"reason": "reminders"}]

    asyncio.run(run_test())


def test_typed_word_only_accepts_exact_confirmation():
    async def run_test():
        answers = []

        async def answer(text, **_kwargs):
            answers.append(text)

        state, _recorded = _state()
        await on_delete_word(SimpleNamespace(text="حذف حساب", answer=answer), state)
        assert answers == [texts.ACCOUNT_DELETE_BAD_WORD]

        answers.clear()
        await on_delete_word(SimpleNamespace(text="  حذف ", answer=answer), state)
        assert answers == [texts.ACCOUNT_DELETE_FINAL]

    asyncio.run(run_test())


def test_non_text_message_in_word_state_is_rejected():
    async def run_test():
        answers = []

        async def answer(text, **_kwargs):
            answers.append(text)

        await on_delete_word_not_text(SimpleNamespace(text=None, answer=answer))
        assert answers == [texts.ACCOUNT_DELETE_BAD_WORD]

    asyncio.run(run_test())


def test_final_confirmation_deletes_account_with_chosen_reason(monkeypatch):
    async def run_test():
        calls = []

        async def fake_delete_account(session, user_id, reason):
            calls.append((user_id, reason))
            return True

        monkeypatch.setattr(users, "delete_account", fake_delete_account)
        commits = []

        class Session:
            async def commit(self):
                commits.append(True)

        state, recorded = _state(data={"reason": "privacy"})
        callback, _answers = _callback("account_del:go")
        await on_delete_confirm(callback, state, Session())

        assert calls == [(777, "privacy")]
        assert commits == [True]
        assert recorded["clears"] == 1

    asyncio.run(run_test())


def test_restore_clears_tombstone_and_renders_home(monkeypatch):
    async def run_test():
        restored = []

        async def fake_restore(session, user_id):
            restored.append(user_id)
            return True

        async def fake_render_home(event, session, tg_user):
            restored.append(("home", tg_user.id))

        monkeypatch.setattr(users, "restore_account", fake_restore)
        monkeypatch.setattr("BOOKzMA.handlers.account.render_home", fake_render_home)

        class Session:
            async def commit(self):
                pass

        callback, _answers = _callback("account_restore")
        await on_account_restore(callback, Session())

        assert restored == [777, ("home", 777)]

    asyncio.run(run_test())


def test_middleware_intercepts_deleted_user_before_handlers(monkeypatch):
    async def run_test():
        answers = []

        async def fake_answer(self, **_kwargs):
            answers.append(self.data)
            return True

        async def fake_is_deleted(_session, user_id):
            return user_id == 777

        async def no_missing_channels(_bot, _user_id):
            return []

        monkeypatch.setattr(users, "is_deleted", fake_is_deleted)
        monkeypatch.setattr(
            "BOOKzMA.middlewares.membership.missing_channels", no_missing_channels
        )
        monkeypatch.setattr(CallbackQuery, "answer", fake_answer)
        middleware = MembershipMiddleware()

        async def no_activity(_event, _data):
            return None

        middleware._record_activity = no_activity
        handled = []

        async def handler(_event, _data):
            handled.append(True)

        def real_callback(data: str, user_id: int) -> CallbackQuery:
            return CallbackQuery(
                id="cb",
                from_user=User(id=user_id, is_bot=False, first_name="Ali"),
                chat_instance="chat",
                data=data,
            )

        deleted = real_callback("read", 777)
        result = await middleware(
            handler,
            deleted,
            {"event_from_user": deleted.from_user, "bot": object(), "session": AsyncSession()},
        )
        assert result is None
        assert handled == []
        assert answers == ["read"]

        alive = real_callback("read", 888)
        await middleware(
            handler,
            alive,
            {"event_from_user": alive.from_user, "bot": object(), "session": AsyncSession()},
        )
        assert handled == [True]

    asyncio.run(run_test())


def test_middleware_skips_direct_messages_channel_updates(monkeypatch):
    async def run_test():
        is_deleted = AsyncMock(side_effect=AssertionError("direct messages must be dropped first"))
        membership_check = AsyncMock(
            side_effect=AssertionError("direct messages must skip membership checks")
        )
        monkeypatch.setattr(users, "is_deleted", is_deleted)
        monkeypatch.setattr(
            "BOOKzMA.middlewares.membership.missing_channels", membership_check
        )
        answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", answer)
        middleware = MembershipMiddleware()
        handled = AsyncMock()

        event = Message(
            message_id=1,
            date=datetime(2026, 11, 3, tzinfo=timezone.utc),
            chat=Chat(id=-100123, type="channel", is_direct_messages=True),
            from_user=User(id=777, is_bot=False, first_name="Ali"),
            text="message from channel DM",
        )
        result = await middleware(
            handled,
            event,
            {"event_from_user": event.from_user, "bot": object(), "session": object()},
        )
        assert result is None
        handled.assert_not_awaited()
        answer.assert_not_awaited()
        is_deleted.assert_not_awaited()
        membership_check.assert_not_awaited()

    asyncio.run(run_test())


def test_middleware_asks_for_join_for_private_non_member(monkeypatch):
    async def run_test():
        answers = []
        monkeypatch.setattr(users, "is_deleted", AsyncMock(return_value=False))
        monkeypatch.setattr("BOOKzMA.middlewares.membership.REQUIRED_CHANNELS", ("required",))

        async def fake_answer(self, text=None, **kwargs):
            answers.append((text, kwargs))

        monkeypatch.setattr(Message, "answer", fake_answer)
        middleware = MembershipMiddleware()

        async def handler(_event, _data):
            raise AssertionError("handler should not run for non-member private user")

        message = Message(
            message_id=1,
            date=datetime(2026, 11, 3, tzinfo=timezone.utc),
            chat=Chat(id=777, type="private"),
            from_user=User(id=777, is_bot=False, first_name="Ali"),
            text="hello",
        )
        await middleware(
            handler,
            message,
            {
                "event_from_user": message.from_user,
                "bot": SimpleNamespace(
                    get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
                ),
                "session": object(),
            },
        )
        assert answers and answers[0][0] == texts.JOIN_GATE

    asyncio.run(run_test())


def test_middleware_ignores_answer_errors_without_traceback(monkeypatch, caplog):
    async def run_test():
        monkeypatch.setattr(users, "is_deleted", AsyncMock(return_value=False))
        monkeypatch.setattr("BOOKzMA.middlewares.membership.REQUIRED_CHANNELS", ("required",))
        middleware = MembershipMiddleware()

        async def fake_answer(*args, **kwargs):
            raise TelegramBadRequest(method=None, message="Bad Request")

        async def handler(_event, _data):
            raise AssertionError("join-gated updates must not reach handlers")

        monkeypatch.setattr(Message, "answer", fake_answer)
        message = Message(
            message_id=1,
            date=datetime(2026, 11, 3, tzinfo=timezone.utc),
            chat=Chat(id=777, type="private"),
            from_user=User(id=777, is_bot=False, first_name="Ali"),
            text="hello",
        )
        result = await middleware(
            handler,
            message,
            {
                "event_from_user": message.from_user,
                "bot": SimpleNamespace(
                    get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
                ),
                "session": object(),
            },
        )
        assert result is None
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].exc_info is None
        assert "\n" not in caplog.records[0].message

    asyncio.run(run_test())


def test_middleware_lets_account_restore_through_for_deleted_user(monkeypatch):
    async def run_test():
        async def fake_is_deleted(_session, user_id):
            return user_id == 777

        monkeypatch.setattr(users, "is_deleted", fake_is_deleted)
        middleware = MembershipMiddleware()
        called = False

        async def handler(_event, _data):
            nonlocal called
            called = True
            return "handled"

        callback = CallbackQuery(
            id="cb",
            from_user=User(id=777, is_bot=False, first_name="Ali"),
            chat_instance="chat",
            data="account_restore",
        )
        result = await middleware(
            handler, callback, {"event_from_user": callback.from_user, "session": AsyncSession()}
        )
        assert result == "handled"
        assert called

    asyncio.run(run_test())
