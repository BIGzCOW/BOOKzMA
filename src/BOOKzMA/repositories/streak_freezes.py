from datetime import date

from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import StreakFreeze, User


async def balance(session: AsyncSession, user_id: int, habit: str = "reading") -> int:
    credited, used = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (StreakFreeze.kind.in_({"earned", "gifted"}), StreakFreeze.quantity),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case((StreakFreeze.kind == "used", StreakFreeze.quantity), else_=0)
                    ),
                    0,
                ),
            ).where(StreakFreeze.user_id == user_id, StreakFreeze.habit == habit)
        )
    ).one()
    return max(0, int(credited) - int(used))


async def used_days(
    session: AsyncSession, user_id: int, habit: str = "reading"
) -> list[date]:
    result = await session.scalars(
        select(StreakFreeze.day).where(
            StreakFreeze.user_id == user_id,
            StreakFreeze.habit == habit,
            StreakFreeze.kind == "used",
        )
    )
    return list(result)


async def lock_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def add_event(
    session: AsyncSession,
    user_id: int,
    kind: str,
    day: date,
    *,
    habit: str = "reading",
    quantity: int = 1,
    operation_id: int | None = None,
) -> bool:
    if habit not in {"reading", "mesbak"}:
        raise ValueError("invalid streak freeze habit")
    if kind in {"earned", "used"}:
        if quantity != 1 or operation_id is not None:
            raise ValueError("earned and used events require quantity one and no operation")
        conflict = dict(
            index_elements=[
                StreakFreeze.user_id,
                StreakFreeze.habit,
                StreakFreeze.kind,
                StreakFreeze.day,
            ],
            index_where=text("kind IN ('earned', 'used')"),
        )
    elif kind == "gifted":
        if quantity < 1 or operation_id is None:
            raise ValueError("gifted events require a positive quantity and operation")
        conflict = dict(index_elements=[StreakFreeze.operation_id, StreakFreeze.user_id])
    else:
        raise ValueError("invalid streak freeze event")
    stmt = (
        insert(StreakFreeze)
        .values(
            user_id=user_id,
            habit=habit,
            kind=kind,
            quantity=quantity,
            day=day,
            operation_id=operation_id,
        )
        .on_conflict_do_nothing(**conflict)
        .returning(StreakFreeze.id)
    )
    return (await session.execute(stmt)).first() is not None