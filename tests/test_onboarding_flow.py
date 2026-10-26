import asyncio
from datetime import date, time, timedelta
from types import SimpleNamespace

from pydantic import SecretStr

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers.onboarding import on_pick_time, on_skip, start_onboarding
from BOOKzMA.handlers.start import cmd_start, is_returning_reader
from BOOKzMA.repositories import users
from BOOKzMA.services.buddy_invites import invite_token_hash

SETTINGS = Settings(bot_token=SecretStr("test"))


def _callback(data: str, user_id: int = 777) -> tuple[SimpleNamespace, list]:
    answers = []

    async def answer(text=None, show_alert=False):
        answers.append((text, show_alert))

    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id, username="ali", full_name="علی"),
        data=data,
        answer=answer,
        message=None,
    ), answers


def _state() -> tuple[SimpleNamespace, dict]:
    recorded = {"clears": 0}

    async def clear() -> None:
        recorded["clears"] += 1

    return SimpleNamespace(clear=clear), recorded


def _user(onboarded: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=777,
        onboarded_at=None if not onboarded else object(),
        timezone="Asia/Tehran",
        display_name="علی",
    )


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def test_is_returning_reader_needs_week_of_silence():
    today = date(2026, 10, 25)
    assert is_returning_reader(None, today) is False
    assert is_returning_reader(today, today) is False
    assert is_returning_reader(today - timedelta(days=7), today) is False
    assert is_returning_reader(today - timedelta(days=8), today) is True


def test_start_onboarding_sends_welcome_with_time_keyboard():
    async def run_test():
        sent = []

        async def answer(text=None, reply_markup=None):
            sent.append((text, reply_markup))

        message = SimpleNamespace(answer=answer)
        state, recorded = _state()
        await start_onboarding(message, Session(), state)

        assert sent == [(texts.ONBOARDING_WELCOME, keyboards.onboarding_time_kb())]
        callback_data = {
            button.callback_data
            for row in sent[0][1].inline_keyboard
            for button in row
        }
        assert "miswak:open" in callback_data
        assert recorded["clears"] == 1

    asyncio.run(run_test())


def test_skip_finishes_onboarding_and_shows_home(monkeypatch):
    async def run_test():
        marked = []
        rendered = []

        async def fake_mark_onboarded(session, user_id):
            marked.append(user_id)
            return True

        async def fake_render_home(event, session, tg):
            rendered.append(tg.id)

        monkeypatch.setattr(users, "mark_onboarded", fake_mark_onboarded)
        monkeypatch.setattr("BOOKzMA.handlers.onboarding.render_home", fake_render_home)
        session = Session()
        callback, answers = _callback("onb:skip")
        state, recorded = _state()
        await on_skip(callback, session, state, SETTINGS)

        assert marked == [777]
        assert rendered == [777]
        assert session.commits == 1
        assert recorded["clears"] == 1
        assert answers == [(texts.ONBOARDING_SKIPPED, False)]

    asyncio.run(run_test())


def test_pick_time_rejects_unknown_payload(monkeypatch):
    async def run_test():
        added = []

        async def fail_add(*args):
            added.append(args)

        monkeypatch.setattr("BOOKzMA.handlers.onboarding.reminders_repo.add", fail_add)
        session = Session()
        callback, answers = _callback("onb:9999")
        state, _recorded = _state()
        await on_pick_time(callback, session, state, SETTINGS)

        assert answers == [(texts.INVALID_ACTION, True)]
        assert added == []
        assert session.commits == 0

    asyncio.run(run_test())


def test_pick_time_creates_first_reminder_and_finishes(monkeypatch):
    async def run_test():
        added = []
        marked = []
        rendered = []

        async def fake_get_or_create(session, user_id, username, *args):
            return _user(onboarded=False)

        async def fake_add(session, user_id, at):
            added.append((user_id, at))
            return "ok"

        async def fake_mark_onboarded(session, user_id):
            marked.append(user_id)
            return True

        async def fake_render_home(event, session, tg):
            rendered.append(tg.id)

        monkeypatch.setattr(users, "get_or_create", fake_get_or_create)
        monkeypatch.setattr("BOOKzMA.handlers.onboarding.reminders_repo.add", fake_add)
        monkeypatch.setattr(users, "mark_onboarded", fake_mark_onboarded)
        monkeypatch.setattr("BOOKzMA.handlers.onboarding.render_home", fake_render_home)

        session = Session()
        callback, answers = _callback("onb:2100")
        state, recorded = _state()
        await on_pick_time(callback, session, state, SETTINGS)

        assert added == [(777, time(21, 0))]
        assert marked == [777]
        assert rendered == [777]
        assert session.commits == 1
        assert answers == [(texts.ONBOARDING_DONE, False)]
        assert recorded["clears"] == 1

    asyncio.run(run_test())


def test_cmd_start_routes_new_user_to_onboarding(monkeypatch):
    async def run_test():
        sent = []

        async def fake_start_onboarding(message, session, state):
            sent.append("onboarding")

        async def fake_get_or_create(*args):
            return _user(onboarded=False)

        monkeypatch.setattr("BOOKzMA.handlers.start.start_onboarding", fake_start_onboarding)
        monkeypatch.setattr(users, "get_or_create", fake_get_or_create)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=777, username="ali", full_name="علی"), answer=None
        )
        state, _recorded = _state()
        await cmd_start(message, Session(), state, SETTINGS)

        assert sent == ["onboarding"]

    asyncio.run(run_test())


def test_cmd_start_accepts_buddy_invite_before_onboarding(monkeypatch):
    async def run_test():
        sent = []
        redeemed = []

        async def fake_start_onboarding(message, session, state):
            sent.append("onboarding")

        async def fake_get_or_create(*args):
            return _user(onboarded=False)

        async def fake_redeem(session, token_hash, recipient_id, now):
            redeemed.append((token_hash, recipient_id))
            return "accepted", 888

        async def fake_get(model, user_id):
            return SimpleNamespace(display_name="دوست")

        async def answer(text=None, **kwargs):
            sent.append(text)

        async def send_message(user_id, text):
            sent.append((user_id, text))

        monkeypatch.setattr("BOOKzMA.handlers.start.start_onboarding", fake_start_onboarding)
        monkeypatch.setattr(users, "get_or_create", fake_get_or_create)
        monkeypatch.setattr("BOOKzMA.handlers.start.buddy_repo.redeem_invite", fake_redeem)

        payload = "buddy_" + "a" * 32
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=777, username="ali", full_name="علی"), answer=answer
        )
        session = Session()
        session.get = fake_get
        state, _recorded = _state()
        bot = SimpleNamespace(send_message=send_message)
        command = SimpleNamespace(args=payload)
        await cmd_start(message, session, state, SETTINGS, command, bot)

        assert redeemed == [(invite_token_hash(payload), 777)]
        assert sent == [
            (888, texts.BUDDY_INVITE_PEER_ACCEPTED.format(name="علی")),
            texts.BUDDY_INVITE_ACCEPTED.format(name="دوست"),
            "onboarding",
        ]

    asyncio.run(run_test())


def test_cmd_start_greets_returning_reader_before_home(monkeypatch):
    async def run_test():
        answers = []

        async def answer(text=None, **kwargs):
            answers.append(text)

        async def fake_render_home(event, session, tg):
            answers.append("home")

        async def fake_last_read_day(session, user_id):
            return date(2026, 10, 1)

        async def fake_get_or_create(*args):
            return _user(onboarded=True)

        monkeypatch.setattr(users, "get_or_create", fake_get_or_create)
        monkeypatch.setattr("BOOKzMA.handlers.start.render_home", fake_render_home)
        monkeypatch.setattr("BOOKzMA.handlers.start.readings.last_read_day", fake_last_read_day)

        message = SimpleNamespace(
            from_user=SimpleNamespace(id=777, username="ali", full_name="علی"), answer=answer
        )
        state, _recorded = _state()
        await cmd_start(message, Session(), state, SETTINGS)

        assert answers == [texts.WELCOME_BACK, "home", "از منوی پایین استفاده کن."]

    asyncio.run(run_test())
