import asyncio
import os
import random
from datetime import date, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import StreakAlert, User
from BOOKzMA.repositories import analytics

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def test_dashboard_reports_comeback_and_risk_kpis():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        today = date(2026, 10, 25)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id, comeback_bonus_days=5))
                session.add(StreakAlert(user_id=user_id, day=today))
                session.add(StreakAlert(user_id=user_id, day=today - timedelta(days=1)))

            async with session_pool() as session:
                stats = await analytics.dashboard(session, today)
                assert stats["comeback_users"] >= 1
                assert stats["streak_alerts_7d"] >= 2

            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(run_test())
