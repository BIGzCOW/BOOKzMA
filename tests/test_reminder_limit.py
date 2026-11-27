import asyncio
import os
import random
from datetime import time

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import User
from BOOKzMA.repositories.reminders import add

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def test_concurrent_additions_respect_five_reminder_limit():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 2_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool() as session:
                session.add(User(id=user_id))
                await session.commit()

            async def add_one(minute: int) -> str:
                async with session_pool.begin() as session:
                    return await add(session, user_id, time(minute // 60, minute % 60))

            results = await asyncio.gather(*(add_one(minute) for minute in range(7)))
            assert results.count("ok") == 5
            assert results.count("limit") == 2
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())
