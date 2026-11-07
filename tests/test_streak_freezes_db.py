import asyncio
import os
import random
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import (
    ActivityDay,
    FreezeGiftOperation,
    FreezeGiftRecipient,
    MesbakChallenge,
    MesbakEntry,
    MesbakProfile,
    ReadingLog,
    StreakFreeze,
    User,
)
from BOOKzMA.repositories import activity, readings, streak_freezes
from BOOKzMA.repositories import freeze_gifts
from BOOKzMA.repositories import mesbak as mesbak_repo
from BOOKzMA.services import mesbak_freezes
from BOOKzMA.services.streak_freezes import on_read

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)


def _user_id() -> int:
    return 3_200_000_000_000_000_000 + random.randrange(1_000_000_000)


def test_freeze_reward_and_use_are_persisted_and_idempotent():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = 3_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        today = date(2026, 10, 21)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))
                await activity.record_interaction(session, user_id, today)
                await activity.record_interaction(session, user_id, today)
                activity_rows = await session.scalar(
                    select(func.count()).select_from(ActivityDay).where(
                        ActivityDay.user_id == user_id, ActivityDay.day == today
                    )
                )
                assert activity_rows == 1
                for offset in range(6, -1, -1):
                    await readings.mark_read(session, user_id, today - timedelta(days=offset))
                reward = await on_read(session, user_id, today)
                assert reward.earned
                assert await streak_freezes.balance(session, user_id) == 1

                assert await readings.mark_read(session, user_id, today + timedelta(days=2))
                protection = await on_read(session, user_id, today + timedelta(days=2))
                assert protection.used_day == today + timedelta(days=1)
                assert await streak_freezes.balance(session, user_id) == 0
                assert not await streak_freezes.add_event(
                    session, user_id, "used", today + timedelta(days=1)
                )
        finally:
            async with session_pool() as session:
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            await engine.dispose()

    asyncio.run(run_test())


def test_freeze_balances_are_separate_and_admin_gifts_are_capped_and_idempotent():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_ids = [_user_id() for _ in range(3)]
        admin_id = _user_id()
        reading_day = date(2026, 10, 20)
        operation_ids = []
        try:
            async with session_pool.begin() as session:
                session.add_all([User(id=user_id) for user_id in user_ids])
                await session.flush()
                session.add_all(
                    [
                        MesbakProfile(user_id=user_ids[0], enabled=True),
                        MesbakProfile(user_id=user_ids[1], enabled=False),
                        MesbakProfile(user_id=user_ids[2], enabled=True),
                        StreakFreeze(
                            user_id=user_ids[0], habit="reading", kind="earned",
                            quantity=1, day=reading_day,
                        ),
                        StreakFreeze(
                            user_id=user_ids[0], habit="reading", kind="earned",
                            quantity=1, day=reading_day + timedelta(days=1),
                        ),
                        *[
                            StreakFreeze(
                                user_id=user_ids[1], habit="reading", kind="earned",
                                quantity=1, day=reading_day + timedelta(days=offset),
                            )
                            for offset in range(3)
                        ],
                    ]
                )

            async with session_pool.begin() as session:
                reading_preview = await freeze_gifts.create_preview(
                    session, admin_id, "reading", 2
                )
                reading_operation_id = reading_preview.operation_id
                operation_ids.append(reading_operation_id)
                snapshot_result = await session.execute(
                    select(
                        FreezeGiftRecipient.user_id,
                        FreezeGiftRecipient.preview_units,
                    ).where(FreezeGiftRecipient.operation_id == reading_operation_id)
                )
                snapshot = {
                    user_id: units for user_id, units in snapshot_result.all()
                }
                assert snapshot[user_ids[0]] == 1
                assert snapshot[user_ids[1]] == 0
                assert snapshot[user_ids[2]] == 2

            async with session_pool.begin() as session:
                result = await freeze_gifts.confirm(
                    session,
                    admin_id,
                    reading_operation_id,
                    datetime.now(timezone.utc),
                )
                assert result is not None and result.status == "completed"
                assert await streak_freezes.balance(session, user_ids[0]) == 3
                assert await streak_freezes.balance(session, user_ids[1]) == 3
                assert await streak_freezes.balance(session, user_ids[2]) == 2
                gifted_count = await session.scalar(
                    select(func.count()).select_from(StreakFreeze).where(
                        StreakFreeze.operation_id == reading_operation_id
                    )
                )

            async with session_pool.begin() as session:
                repeated = await freeze_gifts.confirm(
                    session,
                    admin_id,
                    reading_operation_id,
                    datetime.now(timezone.utc),
                )
                assert repeated is not None and repeated.status == "completed"
                assert await session.scalar(
                    select(func.count()).select_from(StreakFreeze).where(
                        StreakFreeze.operation_id == reading_operation_id
                    )
                ) == gifted_count

            async with session_pool.begin() as session:
                mesbak_preview = await freeze_gifts.create_preview(
                    session, admin_id, "mesbak", 1
                )
                mesbak_operation_id = mesbak_preview.operation_id
                operation_ids.append(mesbak_operation_id)
                assert await session.get(
                    FreezeGiftRecipient, (mesbak_operation_id, user_ids[0])
                ) is not None
                assert await session.get(
                    FreezeGiftRecipient, (mesbak_operation_id, user_ids[2])
                ) is not None
                assert await session.get(
                    FreezeGiftRecipient, (mesbak_operation_id, user_ids[1])
                ) is None

            async with session_pool.begin() as session:
                mesbak_result = await freeze_gifts.confirm(
                    session,
                    admin_id,
                    mesbak_operation_id,
                    datetime.now(timezone.utc),
                )
                assert mesbak_result is not None and mesbak_result.status == "completed"
                assert await streak_freezes.balance(
                    session, user_ids[0], habit="mesbak"
                ) == 1
                assert await streak_freezes.balance(
                    session, user_ids[1], habit="mesbak"
                ) == 0
                assert await streak_freezes.balance(
                    session, user_ids[2], habit="mesbak"
                ) == 1
        finally:
            async with session_pool.begin() as session:
                await session.execute(
                    delete(FreezeGiftOperation).where(
                        FreezeGiftOperation.id.in_(operation_ids)
                    )
                )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            await engine.dispose()

    asyncio.run(run_test())


def test_mesbak_gift_rechecks_cohort_and_operation_owner_before_crediting():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_ids = [_user_id() for _ in range(2)]
        admin_id = _user_id()
        other_admin_id = _user_id()
        operation_id = None
        try:
            async with session_pool.begin() as session:
                session.add_all([User(id=user_id) for user_id in user_ids])
                await session.flush()
                session.add_all(
                    MesbakProfile(user_id=user_id, enabled=True) for user_id in user_ids
                )

            async with session_pool.begin() as session:
                preview = await freeze_gifts.create_preview(
                    session, admin_id, "mesbak", 1
                )
                operation_id = preview.operation_id
                assert preview.recipients == 2

            async with session_pool.begin() as session:
                profile = await session.get(MesbakProfile, user_ids[0])
                profile.enabled = False

            async with session_pool.begin() as session:
                unauthorized = await freeze_gifts.confirm(
                    session, other_admin_id, operation_id, datetime.now(timezone.utc)
                )
                assert unauthorized is None

            async with session_pool.begin() as session:
                changed = await freeze_gifts.confirm(
                    session, admin_id, operation_id, datetime.now(timezone.utc)
                )
                assert changed is not None and changed.status == "changed"
                assert await session.scalar(
                    select(func.count()).select_from(StreakFreeze).where(
                        StreakFreeze.operation_id == operation_id
                    )
                ) == 0

            async with session_pool.begin() as session:
                confirmed = await freeze_gifts.confirm(
                    session, admin_id, operation_id, datetime.now(timezone.utc)
                )
                assert confirmed is not None and confirmed.status == "completed"
                assert await streak_freezes.balance(
                    session, user_ids[0], habit="mesbak"
                ) == 0
                assert await streak_freezes.balance(
                    session, user_ids[1], habit="mesbak"
                ) == 1
        finally:
            async with session_pool.begin() as session:
                if operation_id is not None:
                    await session.execute(
                        delete(FreezeGiftOperation).where(
                            FreezeGiftOperation.id == operation_id
                        )
                    )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
            await engine.dispose()

    asyncio.run(run_test())


def test_mesbak_freeze_does_not_create_activity_reading_or_challenge_progress():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        session_pool = async_sessionmaker(engine, expire_on_commit=False)
        user_id = _user_id()
        today = date(2026, 10, 26)
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)
        try:
            async with session_pool.begin() as session:
                session.add(User(id=user_id))
                await session.flush()
                session.add(
                    MesbakProfile(user_id=user_id, enabled=True, daily_goal=1)
                )
                session.add_all(
                    [
                        MesbakEntry(
                            user_id=user_id, day=two_days_ago, slot=1, daily_goal=1
                        ),
                        MesbakEntry(user_id=user_id, day=today, slot=1, daily_goal=1),
                        MesbakChallenge(
                            user_id=user_id,
                            duration=7,
                            starts_on=today,
                            ends_on=today + timedelta(days=6),
                        ),
                        StreakFreeze(
                            user_id=user_id,
                            habit="mesbak",
                            kind="earned",
                            quantity=1,
                            day=two_days_ago,
                        ),
                    ]
                )

            async with session_pool.begin() as session:
                _challenge, progress_before = await mesbak_repo.challenge_state(
                    session, user_id, today
                )
                assert progress_before == 1

                change = await mesbak_freezes.on_completed_day(session, user_id, today)
                assert change.used_day == yesterday

                challenge, progress_after = await mesbak_repo.challenge_state(
                    session, user_id, today
                )
                assert challenge is not None and challenge.status == "active"
                assert progress_after == progress_before
                assert await session.scalar(
                    select(func.count()).select_from(ActivityDay).where(
                        ActivityDay.user_id == user_id
                    )
                ) == 0
                assert await session.scalar(
                    select(func.count()).select_from(ReadingLog).where(
                        ReadingLog.user_id == user_id
                    )
                ) == 0
                assert await session.scalar(
                    select(func.count()).select_from(MesbakEntry).where(
                        MesbakEntry.user_id == user_id, MesbakEntry.day == yesterday
                    )
                ) == 0
        finally:
            async with session_pool.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            await engine.dispose()

    asyncio.run(run_test())