import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

from BOOKzMA.handlers.mesbak import (
    on_exit_message,
    on_menu_back,
    on_record,
    render_mesbak,
)


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def test_direct_mesbak_entry_marks_new_user_as_started(monkeypatch):
    async def run_test():
        user = SimpleNamespace(
            id=777,
            username="user",
            full_name="User",
            timezone="Asia/Tehran",
            started_at=None,
        )
        started = []
        shown = []

        async def get_or_create(_session, *_args):
            return user

        async def mark_started(_session, user_id):
            started.append(user_id)
            user.started_at = datetime.now(timezone.utc)
            return True

        async def get_profile(_session, _user_id, _today):
            return None

        async def show(_event, text, keyboard):
            shown.append((text, keyboard))

        monkeypatch.setattr("BOOKzMA.handlers.mesbak.users.get_or_create", get_or_create)
        monkeypatch.setattr("BOOKzMA.handlers.mesbak.users.mark_started", mark_started)
        monkeypatch.setattr("BOOKzMA.handlers.mesbak.mesbak_repo.get_profile", get_profile)
        monkeypatch.setattr("BOOKzMA.handlers.mesbak.show", show)

        session = Session()
        await render_mesbak(SimpleNamespace(), session, SimpleNamespace(
            id=777, username="user", full_name="User"
        ))

        assert started == [777]
        assert shown
        assert session.commits == 1

    asyncio.run(run_test())


def test_mesbak_back_restores_the_mesbak_reply_keyboard(monkeypatch):
    from aiogram.types import User as TgUser

    async def run_test():
        rendered = []

        class FakeState:
            async def clear(self):
                return None

        async def capture_render(*args, **kwargs):
            rendered.append((args, kwargs))

        monkeypatch.setattr("BOOKzMA.handlers.mesbak.render_mesbak", capture_render)
        message = SimpleNamespace(
            from_user=TgUser(id=777, is_bot=False, first_name="Reader"),
            text="🔙 مسباک",
        )

        await on_menu_back(message, SimpleNamespace(), FakeState())

        assert rendered[0][1] == {"update_menu": True}

    asyncio.run(run_test())


def test_mesbak_reply_exit_disables_membership_clears_state_and_restores_main_menu(
    monkeypatch,
):
    from aiogram.types import Chat, Message as TgMessage, User as TgUser

    from BOOKzMA import keyboards, texts

    async def run_test():
        sent = []
        disabled = []
        state_cleared = []

        class FakeMessage(TgMessage):
            async def answer(self, text, **kwargs):
                sent.append((text, kwargs.get("reply_markup")))

        class FakeState:
            async def clear(self):
                state_cleared.append(True)

        async def set_enabled(_session, user_id, enabled):
            disabled.append((user_id, enabled))

        async def commit():
            return None

        monkeypatch.setattr("BOOKzMA.handlers.mesbak.mesbak_repo.set_enabled", set_enabled)
        message = FakeMessage(
            message_id=1,
            date=datetime.now(tz=timezone.utc),
            chat=Chat(id=777, type="private"),
            from_user=TgUser(id=777, is_bot=False, first_name="Reader"),
            text="🚪 خروج از مسباک",
        )

        await on_exit_message(message, SimpleNamespace(commit=commit), FakeState())

        assert disabled == [(777, False)]
        assert state_cleared == [True]
        assert sent == [(texts.mesbak_EXITED, keyboards.menu_kb())]

    asyncio.run(run_test())


def test_mesbak_callback_exit_restores_main_reply_keyboard(monkeypatch):
    from aiogram.types import Chat, Message as TgMessage, User as TgUser

    from BOOKzMA import keyboards
    from BOOKzMA.handlers.mesbak import on_exit

    async def run_test():
        sent = []
        disabled = []
        rendered = []
        state_cleared = []

        class FakeMessage(TgMessage):
            async def answer(self, text, **kwargs):
                sent.append((text, kwargs.get("reply_markup")))

        class FakeState:
            async def clear(self):
                state_cleared.append(True)

        async def set_enabled(_session, user_id, enabled):
            disabled.append((user_id, enabled))

        async def render(_event, _session, _tg_user):
            rendered.append(True)

        async def commit():
            return None

        async def answer(*_args, **_kwargs):
            return None

        monkeypatch.setattr("BOOKzMA.handlers.mesbak.mesbak_repo.set_enabled", set_enabled)
        monkeypatch.setattr("BOOKzMA.handlers.mesbak.render_mesbak", render)
        message = FakeMessage(
            message_id=1,
            date=datetime.now(tz=timezone.utc),
            chat=Chat(id=777, type="private"),
            from_user=TgUser(id=777, is_bot=False, first_name="Reader"),
            text="تنظیمات مسباک",
        )
        callback = SimpleNamespace(
            message=message,
            from_user=message.from_user,
            answer=answer,
        )

        await on_exit(callback, SimpleNamespace(commit=commit), FakeState())

        assert disabled == [(777, False)]
        assert state_cleared == [True]
        assert rendered == [True]
        assert len(sent) == 1
        assert sent[0][1] == keyboards.menu_kb()

    asyncio.run(run_test())


def test_mesbak_goal_completion_offers_nudge_to_eligible_buddy(monkeypatch):
    from aiogram.types import Chat, Message as TgMessage

    from BOOKzMA import keyboards, texts
    from BOOKzMA.handlers import mesbak

    async def run_test():
        today = date(2026, 10, 26)
        sent = []

        class FakeMessage(TgMessage):
            async def answer(self, text, **kwargs):
                sent.append((text, kwargs.get("reply_markup")))

        message = FakeMessage(
            message_id=1,
            date=datetime.now(tz=timezone.utc),
            chat=Chat(id=777, type="private"),
            text="نوبت مسباک ثبت شد",
        )
        pair = SimpleNamespace(last_nudge_on=None)
        buddy = SimpleNamespace(id=888, timezone="Asia/Tehran")
        result = SimpleNamespace(
            status="ok", day_complete=True, completed_count=1, daily_goal=1
        )

        async def fake_user_from_callback(_callback, _session):
            return SimpleNamespace(id=777), today, 777

        async def fake_record(*_args):
            return result

        async def fake_completed_days(*_args):
            return {today}

        async def fake_award_badges(*_args):
            return []

        async def fake_buddies(*_args):
            return [(pair, buddy)]

        async def fake_completed_buddies(*_args):
            return set()

        async def fake_render(*_args):
            return None

        async def fake_cleanup(*_args, **_kwargs):
            return None

        async def fake_freeze_change(*_args):
            return SimpleNamespace(used_day=None, earned=False)

        async def fake_used_days(*_args, **_kwargs):
            return []

        async def fake_freeze_balance(*_args, **_kwargs):
            return 0

        async def commit():
            return None

        async def answer(*_args, **_kwargs):
            return None

        monkeypatch.setattr(mesbak, "_user_from_callback", fake_user_from_callback)
        monkeypatch.setattr(mesbak.mesbak_repo, "record_occurrence", fake_record)
        monkeypatch.setattr(mesbak.mesbak_repo, "completed_day_set", fake_completed_days)
        monkeypatch.setattr(mesbak.mesbak_repo, "award_streak_badges", fake_award_badges)
        monkeypatch.setattr(mesbak.mesbak_repo, "buddy_users", fake_buddies)
        monkeypatch.setattr(
            mesbak.mesbak_repo, "users_completed_on_days", fake_completed_buddies
        )
        monkeypatch.setattr(mesbak, "render_mesbak", fake_render)
        monkeypatch.setattr(mesbak, "request_cleanup", fake_cleanup)
        monkeypatch.setattr(mesbak.mesbak_freezes, "on_completed_day", fake_freeze_change)
        monkeypatch.setattr(mesbak.streak_freezes, "used_days", fake_used_days)
        monkeypatch.setattr(mesbak.streak_freezes, "balance", fake_freeze_balance)

        callback = SimpleNamespace(
            data=f"mesbak:done:{today:%Y%m%d}:1",
            from_user=SimpleNamespace(id=777, username="reader", full_name="Reader"),
            answer=answer,
            message=message,
        )
        await on_record(callback, SimpleNamespace(commit=commit), SimpleNamespace())

        assert sent[0][0] == texts.MESBAK_BUDDY_NUDGE_PROMPT
        assert sent[0][1] == keyboards.mesbak_buddy_nudge_prompt_kb()

    asyncio.run(run_test())