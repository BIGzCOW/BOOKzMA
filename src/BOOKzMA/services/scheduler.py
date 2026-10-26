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
from BOOKzMA.repositories import readings
from BOOKzMA.repositories import streak_freezes
from BOOKzMA.repositories import reminders as reminders_repo
from BOOKzMA.services.streak import displayed_streak
from BOOKzMA.utils import local_now

log = logging.getLogger(__name__)

CHECK_EVERY = 30
# یادآوری که بیشتر از این دیر شده (مثلاً ربات خاموش بوده) دیگه فرستاده نمی‌شه
MAX_LATE = timedelta(minutes=10)
MAX_ATTEMPTS_PER_DAY = 3


async def reminder_loop(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> None:
    log.info("reminder loop started")
    while True:
        try:
            await send_due(bot, session_pool)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("reminder loop failed")
        await asyncio.sleep(CHECK_EVERY)


async def send_due(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        rows = await reminders_repo.list_all_with_users(session)
        blocked: set[int] = set()

        for reminder, user in rows:
            if user.id in blocked:
                continue
            now = local_now(user.timezone)
            today = now.date()
            if reminder.last_sent_on == today:
                continue
            if reminder.attempt_date != today:
                reminder.attempt_date = today
                reminder.attempt_count = 0
                reminder.retry_after_until = None
            if reminder.attempt_count >= MAX_ATTEMPTS_PER_DAY:
                continue
            if reminder.retry_after_until is not None and reminder.retry_after_until > now:
                continue
            due = datetime.combine(today, reminder.remind_at, tzinfo=now.tzinfo)
            late = now - due
            if late < timedelta(0) or late > MAX_LATE:
                continue

            # کسی که امروز خونده یادآوری نمی‌گیره
            if await readings.has_read(session, user.id, today):
                reminder.last_sent_on = today
                await session.commit()
                continue

            days = await readings.get_days(session, user.id)
            frozen_days = await streak_freezes.used_days(session, user.id)
            text = texts.reminder_push(
                displayed_streak(
                    days, today, frozen_days, user.comeback_bonus_days, user.comeback_base_day
                )
            )
            reminder.attempt_count += 1
            await session.commit()
            try:
                await bot.send_message(user.id, text, reply_markup=keyboards.reminder_push_kb())
            except TelegramForbiddenError:
                blocked.add(user.id)
                await reminders_repo.delete_all_for_user(session, user.id)
                log.info("user %s blocked the bot, reminders removed", user.id)
            except TelegramRetryAfter as e:
                log.warning("rate limited, retrying after %s s", e.retry_after)
                reminder.retry_after_until = datetime.now(timezone.utc) + timedelta(
                    seconds=e.retry_after
                )
                await session.commit()
                await asyncio.sleep(e.retry_after)
                continue
            except (TelegramNetworkError, TelegramServerError):
                log.exception("temporary Telegram failure for user %s; will retry", user.id)
                await session.commit()
                continue
            except TelegramAPIError:
                log.exception("could not send reminder to %s", user.id)
                reminder.attempt_count = MAX_ATTEMPTS_PER_DAY
                await session.commit()
                continue
            reminder.last_sent_on = today
            reminder.retry_after_until = None
            await session.commit()
            await asyncio.sleep(0.05)
