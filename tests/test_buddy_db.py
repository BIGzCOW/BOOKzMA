import asyncio
import os
import random
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import BuddyInvite, BuddyPair, BuddyQueue, ReadingLog, User
from BOOKzMA.repositories import analytics
from BOOKzMA.repositories import buddy as buddy_repo
from BOOKzMA.repositories import readings as readings_repo
from BOOKzMA.repositories import users as users_repo

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database"
)


def _uid() -> int:
    return 4_000_000_000_000_000_000 + random.randrange(1_000_000_000)


def test_pairing_queue_end_and_rematch():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b, uid_c = _uid(), _uid(), _uid()
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b, uid_c))

            async with session_pool.begin() as session:
                await buddy_repo.join_queue(session, uid_a)
                assert await buddy_repo.try_match(session, uid_a) is None

            async with session_pool.begin() as session:
                await buddy_repo.join_queue(session, uid_b)
                assert await buddy_repo.try_match(session, uid_b) == uid_a

            async with session_pool() as session:
                found = await buddy_repo.active_pair(session, uid_a)
                assert found is not None
                pair, buddy_id = found
                assert buddy_id == uid_b
                assert await buddy_repo.is_queued(session, uid_a) is False

            async with session_pool.begin() as session:
                await buddy_repo.end_pair(session, pair, uid_a)

            async with session_pool() as session:
                assert await buddy_repo.active_pair(session, uid_a) is None

            # نفر سوم و کاربر آزادشده دوباره جفت می‌شوند
            async with session_pool.begin() as session:
                await buddy_repo.join_queue(session, uid_c)
                assert await buddy_repo.try_match(session, uid_c) in (uid_a, uid_b)

            async with session_pool() as session:
                stats = await analytics.dashboard(session, date(2026, 10, 25))
                assert stats["buddy_pairs_total"] >= 2
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b, uid_c])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_nudge_cap_is_once_per_day_and_per_pair():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b = _uid(), _uid()
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b))
                session.add(BuddyPair(user_a=min(uid_a, uid_b), user_b=max(uid_a, uid_b)))

            async with session_pool.begin() as session:
                found = await buddy_repo.active_pair(session, uid_a)
                assert found is not None
                pair, _buddy_id = found
                first_day = date(2026, 10, 25)
                assert await buddy_repo.register_nudge(session, pair, first_day) is True
                assert await buddy_repo.register_nudge(session, pair, first_day) is False
                next_day = first_day + timedelta(days=1)
                assert await buddy_repo.register_nudge(session, pair, next_day) is True
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_account_deletion_cascades_pair_and_queue():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b = _uid(), _uid()
        invite_hash = "e" * 64
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b))
                session.add(BuddyQueue(user_id=uid_a))
                session.add(BuddyPair(user_a=min(uid_a, uid_b), user_b=max(uid_a, uid_b)))
                session.add(
                    BuddyInvite(
                        token_hash=invite_hash,
                        inviter_id=uid_a,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    )
                )

            async with session_pool.begin() as session:
                await users_repo.delete_account(session, uid_a, "privacy")

            async with session_pool() as session:
                assert await buddy_repo.active_pair(session, uid_b) is None
                assert await buddy_repo.is_queued(session, uid_a) is False
                assert await session.get(BuddyInvite, invite_hash) is None

            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == uid_b))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(run_test())


def test_invite_is_one_time_and_busy_users_keep_their_state():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b, uid_c, uid_d = (_uid() for _ in range(4))
        now = datetime(2026, 10, 26, tzinfo=timezone.utc)
        token_a = "a" * 64
        token_c = "c" * 64
        token_d = "d" * 64
        token_e = "e" * 64
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b, uid_c, uid_d))

            async with session_pool.begin() as session:
                assert await buddy_repo.create_invite(
                    session, uid_a, token_a, now + timedelta(days=7)
                )

            async with session_pool.begin() as session:
                assert await buddy_repo.redeem_invite(session, token_a, uid_a, now) == (
                    "self",
                    None,
                )
                assert await buddy_repo.redeem_invite(session, token_a, uid_b, now) == (
                    "accepted",
                    uid_a,
                )

            async with session_pool.begin() as session:
                assert await buddy_repo.redeem_invite(session, token_a, uid_c, now) == (
                    "invalid",
                    None,
                )
                found = await buddy_repo.active_pair(session, uid_a)
                assert found is not None and found[1] == uid_b
                assert await buddy_repo.create_invite(
                    session, uid_c, token_c, now + timedelta(days=7)
                )
                assert await buddy_repo.redeem_invite(session, token_c, uid_b, now) == (
                    "accepted",
                    uid_c,
                )
                assert len(await buddy_repo.active_pairs(session, uid_b)) == 2
                assert await buddy_repo.create_invite(
                    session, uid_c, token_e, now + timedelta(days=7)
                )
                assert await buddy_repo.redeem_invite(session, token_e, uid_b, now) == (
                    "already",
                    uid_c,
                )
                assert len(await buddy_repo.active_pairs(session, uid_b)) == 2

            async with session_pool.begin() as session:
                found = await buddy_repo.active_pair(session, uid_a)
                assert found is not None
                await buddy_repo.end_pair(session, found[0], uid_a)
                assert await buddy_repo.join_queue(session, uid_b)
                assert await buddy_repo.create_invite(
                    session, uid_d, token_d, now + timedelta(days=7)
                )
                assert await buddy_repo.redeem_invite(session, token_d, uid_b, now) == (
                    "busy",
                    None,
                )
                assert await buddy_repo.is_queued(session, uid_b)
                await buddy_repo.leave_queue(session, uid_b)
                assert await buddy_repo.redeem_invite(session, token_d, uid_b, now) == (
                    "accepted",
                    uid_d,
                )
                assert await buddy_repo.create_invite(
                    session, uid_a, token_a, now - timedelta(seconds=1)
                )
                assert await buddy_repo.redeem_invite(session, token_a, uid_a, now) == (
                    "invalid",
                    None,
                )
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b, uid_c, uid_d])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_user_can_keep_multiple_buddies_while_joining_anonymous_queue():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b, uid_c = _uid(), _uid(), _uid()
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b, uid_c))
                session.add_all(
                    [
                        BuddyPair(user_a=min(uid_a, uid_b), user_b=max(uid_a, uid_b)),
                        BuddyPair(user_a=min(uid_a, uid_c), user_b=max(uid_a, uid_c)),
                    ]
                )

            async with session_pool.begin() as session:
                pairs = await buddy_repo.active_pairs(session, uid_a)
                assert {buddy_id for _pair, buddy_id in pairs} == {uid_b, uid_c}
                assert await buddy_repo.active_pair_for_user(session, uid_a, pairs[0][0].id)
                assert await buddy_repo.active_pair_for_user(session, uid_b, pairs[0][0].id)
                assert await buddy_repo.active_pair_for_user(session, uid_c, pairs[0][0].id) is None
                assert await buddy_repo.join_queue(session, uid_a)
                assert await buddy_repo.is_queued(session, uid_a)
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b, uid_c])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_anonymous_queue_skips_existing_buddies():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b, uid_c = _uid(), _uid(), _uid()
        try:
            async with session_pool.begin() as session:
                session.add_all(User(id=uid) for uid in (uid_a, uid_b, uid_c))
                session.add(BuddyPair(user_a=min(uid_a, uid_b), user_b=max(uid_a, uid_b)))

            async with session_pool.begin() as session:
                assert await buddy_repo.join_queue(session, uid_b)

            async with session_pool.begin() as session:
                assert await buddy_repo.join_queue(session, uid_a)

            async with session_pool.begin() as session:
                assert await buddy_repo.join_queue(session, uid_c)
                assert await buddy_repo.try_match(session, uid_a) == uid_c

            async with session_pool() as session:
                buddies_a = await buddy_repo.active_pairs(session, uid_a)
                assert {buddy_id for _pair, buddy_id in buddies_a} == {uid_b, uid_c}
                assert await buddy_repo.is_queued(session, uid_b)
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b, uid_c])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_bulk_read_status_uses_each_buddys_local_day():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        uid_a, uid_b = _uid(), _uid()
        day_a = date(2026, 10, 26)
        day_b = day_a - timedelta(days=1)
        try:
            async with session_pool.begin() as session:
                session.add_all([User(id=uid_a), User(id=uid_b)])
                session.add_all(
                    [ReadingLog(user_id=uid_a, day=day_a), ReadingLog(user_id=uid_b, day=day_b)]
                )

            async with session_pool() as session:
                assert await readings_repo.users_read_on_days(
                    session, [(uid_a, day_a), (uid_b, day_a)]
                ) == {uid_a}
                assert await readings_repo.users_read_on_days(session, [(uid_b, day_b)]) == {uid_b}
                assert await readings_repo.users_read_on_days(session, []) == set()
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id.in_([uid_a, uid_b])))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())
