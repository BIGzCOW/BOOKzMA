import asyncio
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from BOOKzMA.services import miswak_scheduler

TODAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 6, 40, tzinfo=ZoneInfo("Asia/Tehran"))


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


class SessionPool:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return SessionContext(self.session)


def _row(slot: int = 1, goal: int = 3):
    reminder = SimpleNamespace(
        user_id=77,
        slot=slot,
        remind_at=time(6, 30),
        last_sent_on=None,
        attempt_date=TODAY,
        attempt_count=0,
        retry_after_until=None,
    )
    profile = SimpleNamespace(
        daily_goal=goal,
        next_daily_goal=None,
        goal_effective_on=None,
        enabled=True,
    )
    user = SimpleNamespace(id=77, timezone="Asia/Tehran")
    return reminder, profile, user


def _patch_clock_and_rows(monkeypatch, rows, entries):
    async def due_reminders(_session):
        return rows

    async def entries_for_day(_session, _user_id, _day):
        return set(entries)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(miswak_scheduler, "local_now", lambda _timezone: NOW)
    monkeypatch.setattr(miswak_scheduler.miswak_repo, "due_reminders", due_reminders)
    monkeypatch.setattr(
        miswak_scheduler.miswak_repo, "entries_for_day", entries_for_day
    )
    monkeypatch.setattr(miswak_scheduler.asyncio, "sleep", no_sleep)


def test_scheduler_sends_due_occurrence_and_marks_it_sent(monkeypatch):
    async def run_test():
        row = _row(slot=2)
        _patch_clock_and_rows(monkeypatch, [row], {1})
        sent = []

        async def send_message(*args, **kwargs):
            sent.append((args, kwargs))

        session = Session()
        await miswak_scheduler.send_due_miswak_reminders(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )

        assert len(sent) == 1
        assert sent[0][0][0] == 77
        assert row[0].last_sent_on == TODAY
        assert row[0].attempt_count == 1
        assert session.commits == 2

    asyncio.run(run_test())


def test_scheduler_skips_completed_goal(monkeypatch):
    async def run_test():
        row = _row(slot=3)
        _patch_clock_and_rows(monkeypatch, [row], {1, 2, 3})
        sent = []

        async def send_message(*args, **kwargs):
            sent.append((args, kwargs))

        session = Session()
        await miswak_scheduler.send_due_miswak_reminders(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )

        assert sent == []
        assert row[0].last_sent_on == TODAY
        assert session.commits == 1

    asyncio.run(run_test())


def test_scheduler_persists_retry_after(monkeypatch):
    async def run_test():
        row = _row()
        _patch_clock_and_rows(monkeypatch, [row], set())

        async def send_message(*_args, **_kwargs):
            raise TelegramRetryAfter(
                SendMessage(chat_id=77, text="reminder"), "retry", 15
            )

        session = Session()
        await miswak_scheduler.send_due_miswak_reminders(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )

        assert row[0].retry_after_until is not None
        assert row[0].last_sent_on is None
        assert session.commits == 2

    asyncio.run(run_test())


def test_scheduler_removes_reminders_after_user_blocks_bot(monkeypatch):
    async def run_test():
        first = _row(slot=1)
        second = _row(slot=2)
        _patch_clock_and_rows(monkeypatch, [first, second], set())
        removed = []

        async def delete_reminders(_session, user_id):
            removed.append(user_id)

        async def send_message(*_args, **_kwargs):
            raise TelegramForbiddenError(
                SendMessage(chat_id=77, text="reminder"), "bot was blocked"
            )

        monkeypatch.setattr(
            miswak_scheduler.miswak_repo, "delete_reminders", delete_reminders
        )
        session = Session()
        await miswak_scheduler.send_due_miswak_reminders(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )

        assert removed == [77]
        assert first[0].attempt_count == 1
        assert second[0].attempt_count == 0
        assert session.commits == 2

    asyncio.run(run_test())