import asyncio
import os
import random
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import ReminderMessage, User
from BOOKzMA.repositories import reminders as reminders_repo
from BOOKzMA.services import reminder_cleanup, scheduler

TODAY = date(2026, 10, 26)
NOW = datetime(2026, 10, 26, 6, 40, tzinfo=ZoneInfo("Asia/Tehran"))
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def _db_user_id() -> int:
    return 5_000_000_000_000_000_000 + random.randrange(1_000_000_000)


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


def test_process_pending_deletes_messages_and_clears_delivery(monkeypatch):
    async def run_test():
        delivery = SimpleNamespace(id=1, user_id=777, message_id=42)
        deleted = []
        cleared = []

        async def purge(_session, _before):
            return None

        async def list_pending(_session, _now, **_kwargs):
            return [delivery]

        async def mark_deleted(_session, delivery_id):
            cleared.append(delivery_id)

        async def delete_message(chat_id, message_id):
            deleted.append((chat_id, message_id))

        monkeypatch.setattr(reminder_cleanup.reminders, "purge_expired_messages", purge)
        monkeypatch.setattr(reminder_cleanup.reminders, "list_cleanup_pending", list_pending)
        monkeypatch.setattr(reminder_cleanup.reminders, "mark_message_deleted", mark_deleted)
        session = Session()

        count = await reminder_cleanup.process_pending(
            SimpleNamespace(delete_message=delete_message), session, now=NOW
        )

        assert count == 1
        assert deleted == [(777, 42)]
        assert cleared == [1]
        assert session.commits == 1

    asyncio.run(run_test())


def test_process_pending_defers_retry_after(monkeypatch):
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import DeleteMessage

    async def run_test():
        delivery = SimpleNamespace(id=2, user_id=777, message_id=43)
        deferred = []

        async def purge(_session, _before):
            return None

        async def list_pending(_session, _now, **_kwargs):
            return [delivery]

        async def defer(_session, delivery_id, retry_at):
            deferred.append((delivery_id, retry_at))

        async def delete_message(chat_id, message_id):
            assert (chat_id, message_id) == (777, 43)
            raise TelegramRetryAfter(DeleteMessage(chat_id=777, message_id=43), "retry", 10)

        monkeypatch.setattr(reminder_cleanup.reminders, "purge_expired_messages", purge)
        monkeypatch.setattr(reminder_cleanup.reminders, "list_cleanup_pending", list_pending)
        monkeypatch.setattr(reminder_cleanup.reminders, "defer_message_cleanup", defer)
        session = Session()

        count = await reminder_cleanup.process_pending(
            SimpleNamespace(delete_message=delete_message), session, now=NOW
        )

        assert count == 0
        assert deferred == [(2, NOW + reminder_cleanup.timedelta(seconds=10))]

    asyncio.run(run_test())


def test_reading_scheduler_stores_id_and_cleans_racing_delivery(monkeypatch):
    async def run_test():
        reminder = SimpleNamespace(
            id=5,
            remind_at=time(6, 30),
            last_sent_on=None,
            attempt_date=TODAY,
            attempt_count=0,
            retry_after_until=None,
        )
        user = SimpleNamespace(
            id=777,
            timezone="Asia/Tehran",
            comeback_bonus_days=0,
            comeback_base_day=None,
        )
        stored = []
        cleanup = []
        has_read_calls = 0

        async def list_reminders(_session):
            return [(reminder, user)]

        async def process_no_pending(*_args, **_kwargs):
            return 0

        async def has_read(_session, _user_id, _day):
            nonlocal has_read_calls
            has_read_calls += 1
            return has_read_calls == 2

        async def get_days(_session, _user_id):
            return set()

        async def used_days(_session, _user_id):
            return set()

        async def record_message(*args):
            stored.append(args[1:])

        async def request_cleanup(*args, **kwargs):
            cleanup.append((args[2:], kwargs))

        async def send_message(*_args, **_kwargs):
            return SimpleNamespace(message_id=99)

        async def no_sleep(_seconds):
            return None

        monkeypatch.setattr(scheduler, "local_now", lambda _timezone: NOW)
        monkeypatch.setattr(scheduler, "process_pending", process_no_pending)
        monkeypatch.setattr(scheduler.reminders_repo, "list_all_with_users", list_reminders)
        monkeypatch.setattr(scheduler.reminders_repo, "record_message", record_message)
        monkeypatch.setattr(scheduler.readings, "has_read", has_read)
        monkeypatch.setattr(scheduler.readings, "get_days", get_days)
        monkeypatch.setattr(scheduler.streak_freezes, "used_days", used_days)
        monkeypatch.setattr(scheduler, "request_cleanup", request_cleanup)
        monkeypatch.setattr(scheduler.asyncio, "sleep", no_sleep)
        session = Session()

        await scheduler.send_due(
            SimpleNamespace(send_message=send_message), SessionPool(session)
        )

        assert stored == [(777, "reading", 5, TODAY, 99)]
        assert reminder.last_sent_on == TODAY
        assert cleanup and cleanup[0][0] == (777, "reading", TODAY)

    asyncio.run(run_test())


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)
def test_reminder_cleanup_is_scoped_by_owner_habit_day_and_keeps_source_message():
    async def run_test():
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _db_user_id()
        previous_day = TODAY.replace(day=TODAY.day - 1)
        try:
            async with pool.begin() as session:
                session.add(User(id=user_id))

            async with pool.begin() as session:
                await reminders_repo.record_message(
                    session, user_id, "reading", 1, TODAY, 101
                )
                await reminders_repo.record_message(
                    session, user_id, "reading", 2, TODAY, 102
                )
                await reminders_repo.record_message(
                    session, user_id, "mesbak", 1, TODAY, 201
                )
                await reminders_repo.record_message(
                    session, user_id, "reading", 1, previous_day, 301
                )
                await reminders_repo.request_message_cleanup(
                    session,
                    user_id,
                    "reading",
                    TODAY,
                    keep_message_id=101,
                )

            async with pool() as session:
                rows = list(
                    await session.scalars(
                        select(ReminderMessage).where(ReminderMessage.user_id == user_id)
                    )
                )
                state = {
                    row.message_id: row.cleanup_pending
                    for row in rows
                }
                assert state == {102: True, 201: False, 301: False}
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)
def test_reminder_cleanup_retries_racing_delivery_and_cascades_on_account_delete():
    async def run_test():
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _db_user_id()
        retry_at = datetime(2026, 10, 26, 7, 0, tzinfo=ZoneInfo("Asia/Tehran"))
        try:
            async with pool.begin() as session:
                session.add(User(id=user_id))

            async with pool.begin() as session:
                await reminders_repo.record_message(
                    session, user_id, "mesbak", 1, TODAY, 401
                )
                await reminders_repo.request_message_cleanup(
                    session, user_id, "mesbak", TODAY
                )
                await reminders_repo.record_message(
                    session, user_id, "mesbak", 2, TODAY, 402
                )
                await reminders_repo.request_message_cleanup(
                    session, user_id, "mesbak", TODAY
                )
                due = await reminders_repo.list_cleanup_pending(session, NOW, user_id=user_id)
                assert [row.message_id for row in due] == [401, 402]
                await reminders_repo.defer_message_cleanup(session, due[0].id, retry_at)

            async with pool.begin() as session:
                before_retry = await reminders_repo.list_cleanup_pending(
                    session, NOW, user_id=user_id
                )
                after_retry = await reminders_repo.list_cleanup_pending(
                    session, retry_at, user_id=user_id
                )
                assert [row.message_id for row in before_retry] == [402]
                assert [row.message_id for row in after_retry] == [401, 402]
                await session.execute(delete(User).where(User.id == user_id))

            async with pool() as session:
                remaining = await session.scalars(
                    select(ReminderMessage).where(ReminderMessage.user_id == user_id)
                )
                assert list(remaining) == []
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())
