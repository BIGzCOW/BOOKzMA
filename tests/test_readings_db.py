import asyncio
import os
import random
from datetime import date

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import ReadingLog, User
from BOOKzMA.repositories.readings import mark_read

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)


def test_concurrent_same_day_reads_are_idempotent():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        reading_day = date(2026, 10, 27)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))

            async def mark_read_once() -> bool:
                async with session_pool.begin() as session:
                    return await mark_read(session, user_id, reading_day)

            results = await asyncio.gather(*(mark_read_once() for _ in range(8)))
            assert results.count(True) == 1
            assert results.count(False) == 7

            async with session_pool() as session:
                row_count = await session.scalar(
                    select(func.count())
                    .select_from(ReadingLog)
                    .where(ReadingLog.user_id == user_id, ReadingLog.day == reading_day)
                )
                assert row_count == 1
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())
