import asyncio
import os
import random
from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import User
from BOOKzMA.repositories import badges as badges_repo
from BOOKzMA.repositories import analytics

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def test_award_is_idempotent_and_dashboard_counts_it():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))
                assert await badges_repo.award(session, user_id, "first_read", date(2026, 10, 25))
                assert not await badges_repo.award(
                    session, user_id, "first_read", date(2026, 10, 26)
                )
                assert await badges_repo.award(session, user_id, "streak_3", date(2026, 10, 27))

            async with session_pool() as session:
                codes = await badges_repo.list_for_user(session, user_id)
                assert codes == ["first_read", "streak_3"]
                stats = await analytics.dashboard(session, date(2026, 10, 27))
                assert stats["badges_total"] >= 2
                assert stats["badge_holders"] >= 1

            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(run_test())
