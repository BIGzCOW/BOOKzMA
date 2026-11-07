import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.repositories import reminders

log = logging.getLogger(__name__)
CLEANUP_RETRY = timedelta(seconds=30)
MESSAGE_RETENTION = timedelta(hours=48)


async def request_cleanup(
    bot: Bot,
    session: AsyncSession,
    user_id: int,
    habit: str,
    local_day: date,
    *,
    keep_message_id: int | None = None,
    schedule_id: int | None = None,
) -> None:
    await reminders.request_message_cleanup(
        session,
        user_id,
        habit,
        local_day,
        keep_message_id=keep_message_id,
        schedule_id=schedule_id,
    )
    await session.commit()
    await process_pending(bot, session, user_id=user_id)


async def process_pending(
    bot: Bot,
    session: AsyncSession,
    *,
    user_id: int | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> int:
    now = now or datetime.now(timezone.utc)
    await reminders.purge_expired_messages(session, now - MESSAGE_RETENTION)
    deliveries = await reminders.list_cleanup_pending(
        session, now, user_id=user_id, limit=limit
    )
    deleted = 0
    for delivery in deliveries:
        try:
            await bot.delete_message(
                chat_id=delivery.user_id, message_id=delivery.message_id
            )
        except TelegramRetryAfter as error:
            await reminders.defer_message_cleanup(
                session,
                delivery.id,
                now + timedelta(seconds=error.retry_after),
            )
        except (TelegramNetworkError, TelegramServerError):
            await reminders.defer_message_cleanup(
                session, delivery.id, now + CLEANUP_RETRY
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            await reminders.mark_message_deleted(session, delivery.id)
        except TelegramAPIError:
            log.exception("could not delete reminder message for user %s", delivery.user_id)
            await reminders.mark_message_deleted(session, delivery.id)
        else:
            await reminders.mark_message_deleted(session, delivery.id)
            deleted += 1
        await session.commit()
    if not deliveries:
        await session.commit()
    return deleted
