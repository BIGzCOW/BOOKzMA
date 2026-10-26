from datetime import date

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import ReadingLog


async def mark_read(session: AsyncSession, user_id: int, day: date) -> bool:
    """True اگه همین الان ثبت شد، False اگه قبلاً ثبت شده بود"""
    stmt = (
        insert(ReadingLog)
        .values(user_id=user_id, day=day)
        .on_conflict_do_nothing()
        .returning(ReadingLog.user_id)
    )
    result = await session.execute(stmt)
    return result.first() is not None


async def get_days(session: AsyncSession, user_id: int) -> list[date]:
    result = await session.scalars(select(ReadingLog.day).where(ReadingLog.user_id == user_id))
    return list(result)


async def has_read(session: AsyncSession, user_id: int, day: date) -> bool:
    found = await session.scalar(
        select(ReadingLog.user_id).where(ReadingLog.user_id == user_id, ReadingLog.day == day)
    )
    return found is not None


async def users_read_on_days(
    session: AsyncSession, user_days: list[tuple[int, date]]
) -> set[int]:
    """Return users who have a reading row for their own local day."""
    if not user_days:
        return set()
    result = await session.scalars(
        select(ReadingLog.user_id).where(
            tuple_(ReadingLog.user_id, ReadingLog.day).in_(user_days)
        )
    )
    return set(result)


async def last_read_day(session: AsyncSession, user_id: int) -> date | None:
    """آخرین روز محلی ثبت‌شدهٔ مطالعه؛ مبنای تشخیص «کاربر برگشته»."""
    return await session.scalar(
        select(func.max(ReadingLog.day)).where(ReadingLog.user_id == user_id)
    )
