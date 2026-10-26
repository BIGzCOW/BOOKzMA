import asyncio
from datetime import datetime, timezone

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from BOOKzMA.middlewares.rate_limit import RateLimitMiddleware
from BOOKzMA.texts import RATE_LIMITED


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr("BOOKzMA.middlewares.rate_limit.time.monotonic", fake)
    return fake


def _message(monkeypatch):
    answers = []

    async def answer(_self, text=None, **_kwargs):
        answers.append(text)

    monkeypatch.setattr(Message, "answer", answer)
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type="private"),
        text="/start",
    ), answers


def _callback(monkeypatch):
    answers = []

    async def answer(_self, text=None, **_kwargs):
        answers.append(text)

    monkeypatch.setattr(CallbackQuery, "answer", answer)
    return CallbackQuery(
        id="cb",
        from_user=User(id=1, is_bot=False, first_name="U"),
        chat_instance="chat",
        data="menu:home",
    ), answers


def _run(middleware, event, user_id):
    calls = []

    async def handler(_event, _data):
        calls.append(True)
        return "handled"

    from_user = User(id=user_id, is_bot=False, first_name="U")
    result = asyncio.run(
        middleware(handler, event, {"event_from_user": from_user, "bot": object()})
    )
    return result, calls


def test_updates_under_limit_pass(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=3, window_seconds=10)
    event, answers = _message(monkeypatch)
    for _ in range(3):
        result, calls = _run(middleware, event, 1)
        assert result == "handled"
        assert calls == [True]
    assert answers == []


def test_updates_over_limit_are_blocked_and_warned_once_per_window(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=2, window_seconds=10)
    event, answers = _message(monkeypatch)
    assert _run(middleware, event, 1) == ("handled", [True])
    assert _run(middleware, event, 1) == ("handled", [True])
    assert answers == []

    result, calls = _run(middleware, event, 1)
    assert result is None
    assert calls == []
    assert answers == [RATE_LIMITED]

    result, _ = _run(middleware, event, 1)
    assert result is None
    assert answers == [RATE_LIMITED]

    clock.advance(11)
    result, calls = _run(middleware, event, 1)
    assert result == "handled"
    assert calls == [True]


def test_blocked_callback_gets_toast_and_is_swallowed(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=1, window_seconds=10)
    callback, answers = _callback(monkeypatch)
    assert _run(middleware, callback, 1) == ("handled", [True])

    result, calls = _run(middleware, callback, 1)
    assert result is None
    assert calls == []
    assert answers == [RATE_LIMITED]


def test_admin_is_exempt(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=1, window_seconds=10, admin_ids=frozenset({7}))
    event, answers = _message(monkeypatch)
    for _ in range(5):
        result, calls = _run(middleware, event, 7)
        assert result == "handled"
        assert calls == [True]
    assert answers == []


def test_update_without_user_passes(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=1, window_seconds=10)
    event, _answers = _message(monkeypatch)

    async def handler(_event, _data):
        return "handled"

    result = asyncio.run(middleware(handler, event, {}))
    assert result == "handled"


def test_old_users_are_pruned_once_tracked_limit_is_reached(clock, monkeypatch):
    middleware = RateLimitMiddleware(max_updates=1, window_seconds=10)
    event, _answers = _message(monkeypatch)
    _run(middleware, event, 1)
    assert 1 in middleware._hits

    stale_event, _stale = _message(monkeypatch)
    for user_id in range(2, 2 + 1024):
        clock.advance(20)
        _run(middleware, stale_event, user_id)

    assert 1 not in middleware._hits
