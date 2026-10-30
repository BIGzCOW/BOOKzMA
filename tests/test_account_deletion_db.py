import asyncio
import os
import random
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import (
    ActivityDay,
    DeletedAccount,
    PageLog,
    ReadingLog,
    Reminder,
    StreakFreeze,
    User,
    UserBook,
)
from BOOKzMA.repositories import analytics, users
from BOOKzMA.repositories.readings import mark_read

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def test_delete_account_cascades_everything_and_is_idempotent():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id, username="deleteme"))
                await mark_read(session, user_id, date(2026, 10, 20))
                await mark_read(session, user_id, date(2026, 10, 21))
                session.add(StreakFreeze(user_id=user_id, kind="used", day=date(2026, 10, 19)))
                session.add(Reminder(user_id=user_id, remind_at=time(8, 0)))
                session.add(ActivityDay(user_id=user_id, day=date(2026, 10, 21)))
                book = UserBook(user_id=user_id, title="کتاب حذف‌شونده", total_pages=100)
                session.add(book)
                await session.flush()
                session.add(
                    PageLog(
                        user_book_id=book.id,
                        day=date(2026, 10, 21),
                        pages_read=10,
                        source_message_id=55,
                    )
                )
                book_id = book.id

            async with session_pool.begin() as session:
                assert await users.delete_account(session, user_id, "privacy") is True
                assert await users.is_deleted(session, user_id) is True

            async with session_pool() as session:
                assert await _count(session, User, user_id) == 0
                assert await _count(session, ReadingLog, user_id) == 0
                assert await _count(session, StreakFreeze, user_id) == 0
                assert await _count(session, Reminder, user_id) == 0
                assert await _count(session, ActivityDay, user_id) == 0
                assert await _count(session, UserBook, user_id) == 0
                assert await session.scalar(
                    select(func.count()).select_from(PageLog).where(
                        PageLog.user_book_id == book_id
                    )
                ) == 0
                reason = await session.scalar(
                    select(DeletedAccount.reason).where(DeletedAccount.user_id == user_id)
                )
                assert reason == "privacy"
                deleted_at = await session.scalar(
                    select(DeletedAccount.deleted_at).where(DeletedAccount.user_id == user_id)
                )

            async with session_pool.begin() as session:
                assert await users.delete_account(session, user_id, "other") is False

            async with session_pool() as session:
                kept_at = await session.scalar(
                    select(DeletedAccount.deleted_at).where(DeletedAccount.user_id == user_id)
                )
                kept_reason = await session.scalar(
                    select(DeletedAccount.reason).where(DeletedAccount.user_id == user_id)
                )
                assert kept_at == deleted_at
                assert kept_reason == "privacy"
                total, recent = await users.deletion_counts(
                    session, datetime.now(timezone.utc) - timedelta(hours=1)
                )
                assert total >= 1
                assert recent >= 1
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.execute(
                    delete(DeletedAccount).where(DeletedAccount.user_id == user_id)
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_restore_account_allows_registration_again():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))
                await users.delete_account(session, user_id, "unused")

            async with session_pool.begin() as session:
                assert await users.restore_account(session, user_id) is True
                assert await users.is_deleted(session, user_id) is False
                user = await users.get_or_create(session, user_id, None, "دوباره")
                await session.commit()
                assert user.id == user_id
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.execute(
                    delete(DeletedAccount).where(DeletedAccount.user_id == user_id)
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_dashboard_reports_deletion_kpis():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))
                await users.delete_account(session, user_id, "other")

            async with session_pool() as session:
                stats = await analytics.dashboard(session, date(2026, 10, 23))
                assert stats["accounts_deleted"] >= 1
                assert stats["deletions_7d"] >= 1
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.execute(
                    delete(DeletedAccount).where(DeletedAccount.user_id == user_id)
                )
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


async def _count(session, model, user_id: int) -> int:
    column = model.id if model is User else model.user_id
    return (
        await session.scalar(
            select(func.count()).select_from(model).where(column == user_id)
        )
        or 0
    )
