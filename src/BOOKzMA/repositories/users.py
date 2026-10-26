from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import DeletedAccount, ReadingLog, StreakFreeze, User


async def get_or_create(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    display_name: str | None = None,
) -> User:
    stmt = (
        insert(User)
        .values(id=user_id, username=username, display_name=display_name)
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "username": username,
                "broadcast_unavailable": False,
                "display_name": func.coalesce(
                    insert(User).excluded.display_name, User.display_name
                ),
            },
        )
    )
    await session.execute(stmt)
    user = await session.get(User, user_id, populate_existing=True)
    if user is None:
        raise RuntimeError(f"user {user_id} not found after upsert")
    return user


async def set_timezone(session: AsyncSession, user_id: int, tz_name: str) -> None:
    await session.execute(update(User).where(User.id == user_id).values(timezone=tz_name))


async def set_leaderboard_opt_out(session: AsyncSession, user_id: int, opt_out: bool) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(leaderboard_opt_out=opt_out)
    )


async def mark_broadcast_unavailable(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(broadcast_unavailable=True)
    )


async def delete_account(
    session: AsyncSession, user_id: int, reason: str | None = None
) -> bool:
    """حذف کامل حساب: اول سنگ‌قبر، بعد خود کاربر (CASCADE همهٔ جداول وابسته). idempotent."""
    await session.execute(
        insert(DeletedAccount)
        .values(user_id=user_id, reason=reason)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    result = await session.execute(delete(User).where(User.id == user_id))
    return result.rowcount == 1


async def restore_account(session: AsyncSession, user_id: int) -> bool:
    """پاک‌کردن سنگ‌قبر برای ثبت‌نام دوبارهٔ صریح کاربر."""
    result = await session.execute(
        delete(DeletedAccount).where(DeletedAccount.user_id == user_id)
    )
    return result.rowcount == 1


async def is_deleted(session: AsyncSession, user_id: int) -> bool:
    return (
        await session.scalar(
            select(DeletedAccount.user_id).where(DeletedAccount.user_id == user_id)
        )
        is not None
    )


async def deletion_counts(session: AsyncSession, since: datetime | None = None) -> tuple[int, int]:
    """(کل حساب‌های حذف‌شده، حذف‌های بعد از since)"""
    total = await session.scalar(select(func.count()).select_from(DeletedAccount)) or 0
    if since is None:
        return total, 0
    recent = (
        await session.scalar(
            select(func.count())
            .select_from(DeletedAccount)
            .where(DeletedAccount.deleted_at >= since)
        )
        or 0
    )
    return total, recent


async def mark_started(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.started_at.is_(None))
        .values(started_at=datetime.now(timezone.utc))
        .returning(User.id)
    )
    return result.first() is not None


async def mark_onboarded(session: AsyncSession, user_id: int) -> bool:
    """True فقط بار اول؛ فلوی آنبردینگ ایدمپوتنت تمام می‌شود."""
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.onboarded_at.is_(None))
        .values(onboarded_at=datetime.now(timezone.utc))
        .returning(User.id)
    )
    return result.first() is not None


async def leaderboard_rows(
    session: AsyncSession,
) -> list[tuple[int, str | None, str, int, date | None, list, list]]:
    result = await session.execute(
        select(
            User.id,
            User.display_name,
            User.timezone,
            User.comeback_bonus_days,
            User.comeback_base_day,
            ReadingLog.day,
        )
        .join(ReadingLog, ReadingLog.user_id == User.id)
        .where(User.leaderboard_opt_out.is_(False))
        .order_by(User.id, ReadingLog.day)
    )
    rows = result.all()
    user_days: dict[int, tuple[str | None, str, int, date | None, list, list]] = {}
    for user_id, username, timezone_name, bonus_days, bonus_base, day in rows:
        user_days.setdefault(
            user_id, (username, timezone_name, bonus_days, bonus_base, [], [])
        )[4].append(day)
    user_ids = list(user_days)
    if not user_ids:
        return []
    freeze_result = await session.execute(
        select(StreakFreeze.user_id, StreakFreeze.day).where(
            StreakFreeze.kind == "used", StreakFreeze.user_id.in_(user_ids)
        )
    )
    for user_id, day in freeze_result:
        user_days[user_id][5].append(day)
    return [
        (user_id, display_name, timezone_name, bonus_days, bonus_base, days, frozen)
        for user_id, (
            display_name,
            timezone_name,
            bonus_days,
            bonus_base,
            days,
            frozen,
        ) in user_days.items()
    ]
