import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA import keyboards, texts
from BOOKzMA.repositories import mesbak as mesbak_repo
from BOOKzMA.repositories import reminders as reminders_repo
from BOOKzMA.services.reminder_cleanup import process_pending, request_cleanup
from BOOKzMA.services.mesbak import effective_goal, reminder_due
from BOOKzMA.utils import local_now

log = logging.getLogger(__name__)
CHECK_EVERY = 30
MAX_LATE = timedelta(minutes=10)
MAX_ATTEMPTS_PER_DAY = 3


async def mesbak_reminder_loop(
    bot: Bot, session_pool: async_sessionmaker[AsyncSession]
) -> None:
    log.info("mesbak reminder loop started")
    while True:
        try:
            await send_due_mesbak_reminders(bot, session_pool)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("mesbak reminder loop failed")
        await asyncio.sleep(CHECK_EVERY)


async def send_due_mesbak_reminders(
    bot: Bot, session_pool: async_sessionmaker[AsyncSession]
) -> None:
    async with session_pool() as session:
        await process_pending(bot, session)
        rows = await mesbak_repo.due_reminders(session)
        completed_slots: dict[tuple[int, object], set[int]] = {}
        blocked: set[int] = set()

        for reminder, profile, user in rows:
            if user.id in blocked:
                continue
            now = local_now(user.timezone)
            today = now.date()
            goal = effective_goal(
                profile.daily_goal,
                profile.next_daily_goal,
                profile.goal_effective_on,
                today,
            )
            if reminder.slot > goal:
                continue
            if reminder.attempt_date != today:
                reminder.attempt_date = today
                reminder.attempt_count = 0
                reminder.retry_after_until = None
            if not reminder_due(
                now,
                reminder.remind_at,
                reminder.last_sent_on,
                reminder.attempt_count,
                reminder.retry_after_until,
                MAX_LATE,
                MAX_ATTEMPTS_PER_DAY,
            ):
                continue

            key = (user.id, today)
            if key not in completed_slots:
                completed_slots[key] = await mesbak_repo.entries_for_day(session, user.id, today)
            entries = completed_slots[key]
            if reminder.slot in entries or len(entries) >= goal:
                reminder.last_sent_on = today
                await session.commit()
                continue

            reminder.attempt_count += 1
            await session.commit()
            try:
                sent_message = await bot.send_message(
                    user.id,
                    texts.mesbak_reminder(reminder.slot),
                    reply_markup=keyboards.mesbak_reminder_push_kb(
                        today.strftime("%Y%m%d"), reminder.slot
                    ),
                )
            except TelegramForbiddenError:
                blocked.add(user.id)
                await mesbak_repo.delete_reminders(session, user.id)
                await session.commit()
                log.info("user %s blocked the bot, mesbak reminders removed", user.id)
            except TelegramRetryAfter as error:
                reminder.retry_after_until = datetime.now(timezone.utc) + timedelta(
                    seconds=error.retry_after
                )
                await session.commit()
            except (TelegramNetworkError, TelegramServerError):
                log.exception("temporary mesbak reminder failure for user %s", user.id)
                await session.commit()
            except TelegramAPIError:
                log.exception("could not send mesbak reminder to %s", user.id)
                reminder.attempt_count = MAX_ATTEMPTS_PER_DAY
                await session.commit()
            else:
                reminder.last_sent_on = today
                reminder.retry_after_until = None
                await reminders_repo.record_message(
                    session,
                    user.id,
                    "mesbak",
                    reminder.slot,
                    today,
                    sent_message.message_id,
                )
                await session.commit()
                sent_entries = await mesbak_repo.entries_for_day(session, user.id, today)
                if reminder.slot in sent_entries:
                    await request_cleanup(
                        bot,
                        session,
                        user.id,
                        "mesbak",
                        today,
                        schedule_id=None if len(sent_entries) >= goal else reminder.slot,
                    )
                await asyncio.sleep(0.05)