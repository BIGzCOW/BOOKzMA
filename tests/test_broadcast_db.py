import asyncio
import os
import random

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import User
from BOOKzMA.repositories import broadcasts

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)


def test_broadcast_confirmation_and_cancel_are_persisted():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_ids = [
            4_000_000_000_000_000_000 + random.randrange(1_000_000_000),
            4_100_000_000_000_000_000 + random.randrange(1_000_000_000),
        ]
        admin_id = user_ids[0]
        try:
            async with session_pool() as session:
                eligible_before = await session.scalar(
                    select(func.count(User.id)).where(User.broadcast_unavailable.is_(False))
                )
                session.add_all(
                    [
                        User(id=user_ids[0]),
                        User(id=user_ids[1], broadcast_unavailable=True),
                    ]
                )
                await session.commit()

                campaign_id, recipients = await broadcasts.create(
                    session, admin_id, "A new update is available."
                )
                await session.commit()
                expected_recipients = eligible_before + 1
                assert recipients == expected_recipients
                assert await broadcasts.start(session, campaign_id, admin_id)
                assert not await broadcasts.start(session, campaign_id, admin_id + 1)

                counts = await broadcasts.campaign_counts(session, campaign_id)
                assert counts == {"pending": expected_recipients}
                assert await broadcasts.cancel(session, campaign_id, admin_id)
                await session.commit()
                assert await broadcasts.campaign_counts(session, campaign_id) == {
                    "cancelled": expected_recipients
                }
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())