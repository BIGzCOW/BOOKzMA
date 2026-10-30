import asyncio
import os
import random
from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import PageLog, ReadingLog, User
from BOOKzMA.repositories import analytics
from BOOKzMA.repositories import books as books_repo
from BOOKzMA.services.reading_registration import register_reading

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)


def _user_id() -> int:
    return 4_500_000_000_000_000_000 + random.randrange(1_000_000_000)


def test_multiple_page_logs_same_day_are_idempotent_per_message_and_mark_reading():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _user_id()
        reading_day = date(2026, 10, 28)
        try:
            async with pool.begin() as session:
                session.add(User(id=user_id, timezone="Asia/Tehran"))
            async with pool.begin() as session:
                status, book = await books_repo.add(
                    session, user_id, "کتاب آزمایشی", None, 100
                )
                assert status == "ok" and book is not None
                book_id = book.id

            async with pool.begin() as session:
                user = await session.get(User, user_id)
                first = await books_repo.log_pages(
                    session, user_id, book_id, reading_day, 10, 101
                )
                assert first.status == "ok"
                registration = await register_reading(session, user, reading_day)
                assert registration.created is True

            async with pool.begin() as session:
                user = await session.get(User, user_id)
                second = await books_repo.log_pages(
                    session, user_id, book_id, reading_day, 10, 102
                )
                assert second.status == "ok"
                registration = await register_reading(session, user, reading_day)
                assert registration.created is False
                duplicate = await books_repo.log_pages(
                    session, user_id, book_id, reading_day, 10, 102
                )
                assert duplicate.status == "duplicate"
                assert duplicate.progress is not None
                assert duplicate.progress.pages_read == 20

            async with pool() as session:
                assert await session.scalar(
                    select(func.count()).select_from(PageLog).where(
                        PageLog.user_book_id == book_id
                    )
                ) == 2
                assert await session.scalar(
                    select(func.count()).select_from(ReadingLog).where(
                        ReadingLog.user_id == user_id,
                        ReadingLog.day == reading_day,
                    )
                ) == 1
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())


def test_concurrent_book_additions_respect_active_limit():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _user_id()
        try:
            async with pool.begin() as session:
                session.add(User(id=user_id))

            async def add_one(number: int) -> str:
                async with pool.begin() as session:
                    status, _book = await books_repo.add(
                        session, user_id, f"کتاب {number}", None, 100
                    )
                    return status

            results = await asyncio.gather(*(add_one(number) for number in range(12)))
            assert results.count("ok") == 10
            assert results.count("limit") == 2
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "pages,message_ids,expected_statuses,expected_total",
    [
        (60, (301, 302), ["ok", "over"], 60),
        (10, (301, 301), ["duplicate", "ok"], 10),
    ],
)
def test_concurrent_page_logs_respect_remaining_pages_and_message_uniqueness(
    pages, message_ids, expected_statuses, expected_total
):
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _user_id()
        try:
            async with pool.begin() as session:
                session.add(User(id=user_id))
            async with pool.begin() as session:
                status, book = await books_repo.add(session, user_id, "کتاب هم‌زمان", None, 100)
                assert status == "ok" and book is not None
                book_id = book.id

            async def log_one(message_id):
                async with pool.begin() as session:
                    result = await books_repo.log_pages(
                        session, user_id, book_id, date(2026, 10, 29), pages, message_id
                    )
                    return result.status

            statuses = await asyncio.gather(*(log_one(mid) for mid in message_ids))
            assert sorted(statuses) == expected_statuses
            async with pool() as session:
                progress = await books_repo.get_progress(session, user_id, book_id)
                assert progress is not None
                assert progress.pages_read == expected_total
                assert progress.book.status == "reading"
                foreign = await books_repo.log_pages(
                    session, user_id + 1, book_id, date(2026, 10, 29), 1, 400
                )
                assert foreign.status == "missing"
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())


def test_progress_finishing_ownership_archive_and_admin_kpis():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        owner_id = _user_id()
        other_id = _user_id()
        reading_day = date(2026, 10, 28)
        try:
            async with pool.begin() as session:
                session.add_all([User(id=owner_id), User(id=other_id)])
            async with pool.begin() as session:
                status, book = await books_repo.add(session, owner_id, "کوتاه", "نویسنده", 20)
                assert status == "ok" and book is not None
                book_id = book.id

            async with pool.begin() as session:
                first = await books_repo.log_pages(
                    session, owner_id, book_id, reading_day, 15, 201
                )
                assert first.status == "ok"
                over = await books_repo.log_pages(
                    session, owner_id, book_id, reading_day, 6, 202
                )
                assert over.status == "over"
                assert await books_repo.get_progress(session, other_id, book_id) is None
                assert await books_repo.archive(session, other_id, book_id) is False

            async with pool.begin() as session:
                finished = await books_repo.log_pages(
                    session, owner_id, book_id, reading_day, 5, 203
                )
                assert finished.status == "ok"
                assert finished.progress is not None
                assert finished.progress.book.status == "finished"
                assert finished.progress.pages_read == 20
                assert await books_repo.log_pages(
                    session, owner_id, book_id, reading_day, 1, 204
                ) == books_repo.PageLogResult(
                    "finished", finished.progress
                )

            async with pool() as session:
                stats = await analytics.dashboard(session, reading_day)
                assert stats["finished_books"] >= 1
                assert stats["pages_7d"] >= 20

            async with pool.begin() as session:
                assert await books_repo.archive(session, owner_id, book_id) is True
                progress = await books_repo.get_progress(session, owner_id, book_id)
                assert progress is not None
                assert progress.book.status == "archived"
                assert progress.pages_read == 20
        finally:
            async with pool.begin() as session:
                await session.execute(delete(User).where(User.id.in_([owner_id, other_id])))
            await engine.dispose()

    asyncio.run(run_test())
