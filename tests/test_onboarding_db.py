import asyncio
import os
import random
from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import User
from BOOKzMA.repositories import analytics, readings, users

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def test_mark_onboarded_is_idempotent_and_dashboard_counts_it():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id, started_at=None))
                assert await users.mark_onboarded(session, user_id) is True
                assert await users.mark_onboarded(session, user_id) is False

            async with session_pool() as session:
                assert await readings.last_read_day(session, user_id) is None

            async with session_pool.begin() as session:
                await readings.mark_read(session, user_id, date(2026, 10, 20))
                await readings.mark_read(session, user_id, date(2026, 10, 24))

            async with session_pool() as session:
                assert await readings.last_read_day(session, user_id) == date(2026, 10, 24)
                stats = await analytics.dashboard(session, date(2026, 10, 25))
                assert stats["onboarded"] >= 1
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())
