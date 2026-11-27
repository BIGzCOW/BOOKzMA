from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import ActivityDay


async def record_interaction(session: AsyncSession, user_id: int, day: date) -> None:
    stmt = insert(ActivityDay).values(user_id=user_id, day=day)
    await session.execute(stmt.on_conflict_do_nothing(index_elements=["user_id", "day"]))
