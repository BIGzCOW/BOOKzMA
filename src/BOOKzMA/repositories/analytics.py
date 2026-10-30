from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import (
    ActivityDay,
    Badge,
    BuddyPair,
    MesbakEntry,
    MesbakBuddyPair,
    MesbakBuddyQueue,
    MesbakProfile,
    PageLog,
    ReadingLog,
    Reminder,
    StreakAlert,
    StreakFreeze,
    User,
    UserBook,
)
from BOOKzMA.repositories import users
from BOOKzMA.services.streak import compute_streak, longest_streak
from BOOKzMA.utils import local_today


async def dashboard(session: AsyncSession, today: date) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)
    counts = {
        "users": await session.scalar(select(func.count()).select_from(User)) or 0,
        "starters": await session.scalar(
            select(func.count()).select_from(User).where(User.started_at.is_not(None))
        )
        or 0,
        "onboarded": await session.scalar(
            select(func.count()).select_from(User).where(User.onboarded_at.is_not(None))
        )
        or 0,
        "starts_7d": await session.scalar(
            select(func.count()).select_from(User).where(
                User.started_at >= now - timedelta(days=7)
            )
        )
        or 0,
        "starts_30d": await session.scalar(
            select(func.count()).select_from(User).where(
                User.started_at >= now - timedelta(days=30)
            )
        )
        or 0,
        "dau": await _active_users(session, today, today),
        "wau": await _active_users(session, seven_days_ago, today),
        "mau": await _active_users(session, thirty_days_ago, today),
        "readers_7d": await _readers(session, seven_days_ago, today),
        "readers_30d": await _readers(session, thirty_days_ago, today),
        "reading_days_7d": await _reading_days(session, seven_days_ago, today),
        "reading_days_30d": await _reading_days(session, thirty_days_ago, today),
        "active_books": await session.scalar(
            select(func.count()).select_from(UserBook).where(UserBook.status == "reading")
        )
        or 0,
        "finished_books": await session.scalar(
            select(func.count()).select_from(UserBook).where(UserBook.finished_at.is_not(None))
        )
        or 0,
        "pages_7d": await session.scalar(
            select(func.coalesce(func.sum(PageLog.pages_read), 0)).where(
                PageLog.day.between(seven_days_ago, today)
            )
        )
        or 0,
        "reminders": await session.scalar(select(func.count()).select_from(Reminder)) or 0,
        "freezes_used": await session.scalar(
            select(func.count()).select_from(StreakFreeze).where(StreakFreeze.kind == "used")
        )
        or 0,
        "streak_alerts_7d": await session.scalar(
            select(func.count()).select_from(StreakAlert).where(StreakAlert.day >= seven_days_ago)
        )
        or 0,
        "comeback_users": await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.comeback_bonus_days > 0)
        )
        or 0,
    }
    counts["inactive_30d"] = await _inactive_starters(session, thirty_days_ago)
    counts.update(await retention_rates(session, today))
    counts.update(await streak_stats(session))
    counts.update(await badges_stats(session))
    counts.update(await buddy_stats(session))
    counts.update(await mesbak_stats(session, today))
    deleted_total, deleted_recent = await users.deletion_counts(
        session, now - timedelta(days=7)
    )
    counts["accounts_deleted"] = deleted_total
    counts["deletions_7d"] = deleted_recent
    return counts


async def activity_series(
    session: AsyncSession, today: date, days: int = 7
) -> list[tuple[date, int]]:
    start = today - timedelta(days=days - 1)
    result = await session.execute(
        select(ActivityDay.day, func.count())
        .where(ActivityDay.day.between(start, today))
        .group_by(ActivityDay.day)
        .order_by(ActivityDay.day)
    )
    counts = dict(result.all())
    return [(start + timedelta(days=offset), counts.get(start + timedelta(days=offset), 0))
            for offset in range(days)]


async def _active_users(session: AsyncSession, start: date, end: date) -> int:
    return await session.scalar(
        select(func.count(func.distinct(ActivityDay.user_id))).where(
            ActivityDay.day.between(start, end)
        )
    ) or 0


async def _inactive_starters(session: AsyncSession, since: date) -> int:
    observed_since = datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)
    has_recent_activity = (
        select(ActivityDay.user_id)
        .where(ActivityDay.user_id == User.id, ActivityDay.day >= since)
        .exists()
    )
    return await session.scalar(
        select(func.count()).select_from(User).where(
            User.started_at < observed_since, ~has_recent_activity
        )
    ) or 0


async def _readers(session: AsyncSession, start: date, end: date) -> int:
    created_day_utc = _utc_day(ReadingLog.created_at)
    return await session.scalar(
        select(func.count(func.distinct(ReadingLog.user_id))).where(
            created_day_utc.between(start, end)
        )
    ) or 0


async def _reading_days(session: AsyncSession, start: date, end: date) -> int:
    created_day_utc = _utc_day(ReadingLog.created_at)
    return await session.scalar(
        select(func.count()).select_from(ReadingLog).where(created_day_utc.between(start, end))
    ) or 0


async def retention_rates(session: AsyncSession, today: date) -> dict[str, int]:
    started_day = _utc_day(User.started_at)
    rates = {}
    for days in (1, 7, 30):
        cohort_start = today - timedelta(days=days + 89)
        cohort_end = today - timedelta(days=days)
        cohort = User.started_at.is_not(None) & started_day.between(cohort_start, cohort_end)
        total = await session.scalar(select(func.count()).select_from(User).where(cohort)) or 0
        returned = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                cohort,
                select(ActivityDay.user_id)
                .where(
                    ActivityDay.user_id == User.id,
                    ActivityDay.day == started_day + days,
                )
                .exists(),
            )
        ) or 0
        rates[f"retention_d{days}"] = round(returned * 100 / total) if total else 0
    return rates


def _utc_day(column):
    return cast(func.timezone("UTC", column), Date)


async def badges_stats(session: AsyncSession) -> dict[str, int]:
    total = await session.scalar(select(func.count()).select_from(Badge)) or 0
    holders = await session.scalar(select(func.count(func.distinct(Badge.user_id)))) or 0
    return {"badges_total": total, "badge_holders": holders}


async def buddy_stats(session: AsyncSession) -> dict[str, int]:
    active = (
        await session.scalar(
            select(func.count()).select_from(BuddyPair).where(BuddyPair.status == "active")
        )
        or 0
    )
    total = await session.scalar(select(func.count()).select_from(BuddyPair)) or 0
    return {"buddy_pairs_active": active, "buddy_pairs_total": total}
async def mesbak_stats(session: AsyncSession, today: date) -> dict[str, int]:
    seven_days_ago = today - timedelta(days=6)
    thirty_days_ago = today - timedelta(days=29)
    daily = (
        select(
            MesbakEntry.user_id.label("user_id"),
            MesbakEntry.day.label("day"),
            func.count().label("done"),
            func.max(MesbakEntry.daily_goal).label("goal"),
        )
        .join(MesbakProfile, MesbakProfile.user_id == MesbakEntry.user_id)
        .where(MesbakProfile.enabled.is_(True))
        .group_by(MesbakEntry.user_id, MesbakEntry.day)
        .subquery()
    )
    enabled_members = await session.scalar(
        select(func.count()).select_from(MesbakProfile).where(MesbakProfile.enabled.is_(True))
    ) or 0
    active_7d = await session.scalar(
        select(func.count(func.distinct(MesbakEntry.user_id)))
        .join(MesbakProfile, MesbakProfile.user_id == MesbakEntry.user_id)
        .where(
            MesbakProfile.enabled.is_(True),
            MesbakEntry.day.between(seven_days_ago, today),
        )
    ) or 0
    active_30d = await session.scalar(
        select(func.count(func.distinct(MesbakEntry.user_id)))
        .join(MesbakProfile, MesbakProfile.user_id == MesbakEntry.user_id)
        .where(
            MesbakProfile.enabled.is_(True),
            MesbakEntry.day.between(thirty_days_ago, today),
        )
    ) or 0
    active_days_7d = await session.scalar(
        select(func.count()).select_from(daily).where(daily.c.day.between(seven_days_ago, today))
    ) or 0
    completed_days_7d = await session.scalar(
        select(func.count())
        .select_from(daily)
        .where(
            daily.c.day.between(seven_days_ago, today),
            daily.c.done >= daily.c.goal,
        )
    ) or 0
    active_pairs = await session.scalar(
        select(func.count()).select_from(MesbakBuddyPair).where(
            MesbakBuddyPair.status == "active"
        )
    ) or 0
    anonymous_pairs = await session.scalar(
        select(func.count()).select_from(MesbakBuddyPair).where(
            MesbakBuddyPair.status == "active",
            MesbakBuddyPair.pair_type == "random",
        )
    ) or 0
    anonymous_waiting = await session.scalar(
        select(func.count()).select_from(MesbakBuddyQueue)
    ) or 0
    return {
        "mesbak_members": enabled_members,
        "mesbak_active_7d": active_7d,
        "mesbak_active_30d": active_30d,
        "mesbak_completed_days_7d": completed_days_7d,
        "mesbak_completion_rate_7d": round(completed_days_7d * 100 / active_days_7d)
        if active_days_7d
        else 0,
        "mesbak_buddy_pairs": active_pairs,
        "mesbak_random_pairs": anonymous_pairs,
        "mesbak_random_waiting": anonymous_waiting,
    }


async def streak_stats(session: AsyncSession) -> dict[str, int]:
    read_result = await session.execute(
        select(ReadingLog.user_id, User.timezone, ReadingLog.day)
        .join(User, User.id == ReadingLog.user_id)
        .order_by(ReadingLog.user_id, ReadingLog.day)
    )
    readings: dict[int, tuple[str, list[date], list[date]]] = {}
    for user_id, timezone_name, day in read_result:
        readings.setdefault(user_id, (timezone_name, [], []))[1].append(day)
    freeze_result = await session.execute(
        select(StreakFreeze.user_id, StreakFreeze.day).where(StreakFreeze.kind == "used")
    )
    for user_id, day in freeze_result:
        if user_id in readings:
            readings[user_id][2].append(day)
    current_streaks = []
    best_streak = 0
    for timezone_name, read_days, frozen_days in readings.values():
        current = compute_streak(read_days, local_today(timezone_name), frozen_days)
        if current:
            current_streaks.append(current)
        best_streak = max(best_streak, longest_streak(read_days, frozen_days))
    return {
        "users_with_streak": len(current_streaks),
        "max_current_streak": max(current_streaks, default=0),
        "max_record_streak": best_streak,
    }
