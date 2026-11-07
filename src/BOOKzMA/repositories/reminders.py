from datetime import date, datetime, time

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.constants import MAX_REMINDERS
from BOOKzMA.db.models import Reminder, ReminderMessage, User


async def list_for_user(session: AsyncSession, user_id: int) -> list[Reminder]:
    result = await session.scalars(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at)
    )
    return list(result)


async def add(session: AsyncSession, user_id: int, at: time) -> str:
    """نتیجه: ok / limit / dup"""
    # Serialize additions for a user so concurrent requests cannot pass the cap.
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    count = await session.scalar(
        select(func.count()).select_from(Reminder).where(Reminder.user_id == user_id)
    )
    if (count or 0) >= MAX_REMINDERS:
        return "limit"
    stmt = (
        insert(Reminder)
        .values(user_id=user_id, remind_at=at)
        .on_conflict_do_nothing()
        .returning(Reminder.id)
    )
    result = await session.execute(stmt)
    return "ok" if result.first() is not None else "dup"


async def delete_one(session: AsyncSession, user_id: int, reminder_id: int) -> bool:
    result = await session.execute(
        delete(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    )
    return result.rowcount > 0


async def delete_all_for_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(delete(Reminder).where(Reminder.user_id == user_id))


async def list_all_with_users(session: AsyncSession) -> list[tuple[Reminder, User]]:
    result = await session.execute(select(Reminder, User).join(User, User.id == Reminder.user_id))
    return [(reminder, user) for reminder, user in result.all()]


async def record_message(
    session: AsyncSession,
    user_id: int,
    habit: str,
    schedule_id: int,
    local_day: date,
    message_id: int,
) -> None:
    session.add(
        ReminderMessage(
            user_id=user_id,
            habit=habit,
            schedule_id=schedule_id,
            local_day=local_day,
            message_id=message_id,
        )
    )
    await session.flush()


async def request_message_cleanup(
    session: AsyncSession,
    user_id: int,
    habit: str,
    local_day: date,
    *,
    keep_message_id: int | None = None,
    schedule_id: int | None = None,
) -> None:
    conditions = [
        ReminderMessage.user_id == user_id,
        ReminderMessage.habit == habit,
        ReminderMessage.local_day == local_day,
    ]
    if schedule_id is not None:
        conditions.append(ReminderMessage.schedule_id == schedule_id)
    if keep_message_id is not None:
        await session.execute(
            delete(ReminderMessage).where(
                *conditions,
                ReminderMessage.message_id == keep_message_id,
            )
        )
        conditions.append(ReminderMessage.message_id != keep_message_id)
    await session.execute(
        update(ReminderMessage)
        .where(*conditions)
        .values(cleanup_pending=True, retry_after_until=None)
    )


async def list_cleanup_pending(
    session: AsyncSession,
    now: datetime,
    *,
    user_id: int | None = None,
    limit: int = 100,
) -> list[ReminderMessage]:
    statement = (
        select(ReminderMessage)
        .where(
            ReminderMessage.cleanup_pending.is_(True),
            (ReminderMessage.retry_after_until.is_(None))
            | (ReminderMessage.retry_after_until <= now),
        )
        .order_by(ReminderMessage.id)
        .limit(limit)
    )
    if user_id is not None:
        statement = statement.where(ReminderMessage.user_id == user_id)
    result = await session.scalars(statement)
    return list(result)


async def mark_message_deleted(session: AsyncSession, delivery_id: int) -> None:
    await session.execute(delete(ReminderMessage).where(ReminderMessage.id == delivery_id))


async def defer_message_cleanup(
    session: AsyncSession, delivery_id: int, retry_after_until: datetime
) -> None:
    await session.execute(
        update(ReminderMessage)
        .where(ReminderMessage.id == delivery_id)
        .values(retry_after_until=retry_after_until)
    )


async def purge_expired_messages(session: AsyncSession, before: datetime) -> None:
    await session.execute(delete(ReminderMessage).where(ReminderMessage.created_at < before))
