from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import Badge


async def award(session: AsyncSession, user_id: int, code: str, day: date) -> bool:
    """True فقط اگر همین حالا اهدا شد (ایدمپوتنت)."""
    stmt = (
        insert(Badge)
        .values(user_id=user_id, code=code, awarded_day=day)
        .on_conflict_do_nothing(index_elements=["user_id", "code"])
        .returning(Badge.id)
    )
    return (await session.execute(stmt)).first() is not None


async def list_for_user(session: AsyncSession, user_id: int) -> list[str]:
    result = await session.scalars(
        select(Badge.code).where(Badge.user_id == user_id).order_by(Badge.awarded_day, Badge.id)
    )
    return list(result)
