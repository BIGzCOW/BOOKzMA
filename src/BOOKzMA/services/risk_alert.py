"""هشدار روزانهٔ «استریک در خطر» (S-08).

هر روز ساعت ۲۱:۰۰ به وقت محلی کاربر، در پنجرهٔ ۱۰ دقیقه‌ای، به کاربری که
استریک واقعی ≥۲ دارد و امروز نخوانده یک پیام با دکمهٔ ثبت مطالعه می‌رود.
dedup با جدول streak_alerts است؛ اگر ربات در پنجره خاموش باشد آن روز هشداری نمی‌رود.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import time, timedelta
from datetime import date as date_type
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA import keyboards, texts
from BOOKzMA.db.models import ReadingLog, StreakAlert, StreakFreeze, User
from BOOKzMA.services.streak import compute_streak
from BOOKzMA.utils import local_now, local_today

log = logging.getLogger(__name__)

CHECK_EVERY = 60
RISK_ALERT_TIME = time(21, 0)
SEND_WINDOW = timedelta(minutes=10)
# پنجرهٔ کاندیداها بر حسب روز UTC؛ برای پوشش اختلاف منطقه‌های زمانی کافی است
LOOKBACK_DAYS = 4
MIN_STREAK_AT_RISK = 2


def is_at_risk(
    today: date_type, read_days: set[date_type], frozen_days: set[date_type]
) -> bool:
    """استریک واقعی ≥۲ که تا دیروز ادامه داشته و امروز هنوز ثبت نشده."""
    if today in read_days:
        return False
    merged = read_days | frozen_days
    yesterday = today - timedelta(days=1)
    if yesterday not in merged:
        return False
    return compute_streak(merged, yesterday) >= MIN_STREAK_AT_RISK


def _in_send_window(now: datetime) -> bool:
    window_end = (
        datetime.combine(now.date(), RISK_ALERT_TIME, tzinfo=now.tzinfo) + SEND_WINDOW
    )
    return RISK_ALERT_TIME <= now.time() < window_end.time()


async def send_risk_alerts(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> int:
    async with session_pool() as session:
        utc_today = datetime.now(timezone.utc).date()
        window_start = utc_today - timedelta(days=LOOKBACK_DAYS)

        users_rows = await session.execute(
            select(User.id, User.timezone).where(User.broadcast_unavailable.is_(False))
        )
        read_rows = await session.execute(
            select(ReadingLog.user_id, ReadingLog.day).where(ReadingLog.day >= window_start)
        )
        freeze_rows = await session.execute(
            select(StreakFreeze.user_id, StreakFreeze.day).where(
                StreakFreeze.kind == "used", StreakFreeze.day >= window_start
            )
        )
        alerted_rows = await session.execute(
            select(StreakAlert.user_id, StreakAlert.day).where(StreakAlert.day >= window_start)
        )

        reads: dict[int, set[date_type]] = defaultdict(set)
        for user_id, day in read_rows:
            reads[user_id].add(day)
        frozen: dict[int, set[date_type]] = defaultdict(set)
        for user_id, day in freeze_rows:
            frozen[user_id].add(day)
        alerted = set(alerted_rows.all())

        sent = 0
        for user_id, timezone_name in users_rows:
            today = local_today(timezone_name)
            if (user_id, today) in alerted:
                continue
            now = local_now(timezone_name)
            if not _in_send_window(now):
                continue
            if not is_at_risk(today, reads.get(user_id, set()), frozen.get(user_id, set())):
                continue

            stmt = (
                insert(StreakAlert)
                .values(user_id=user_id, day=today)
                .on_conflict_do_nothing()
                .returning(StreakAlert.user_id)
            )
            if (await session.execute(stmt)).first() is None:
                await session.commit()
                continue
            await session.commit()
            try:
                await bot.send_message(
                    user_id, texts.RISK_ALERT, reply_markup=keyboards.reminder_push_kb()
                )
                sent += 1
            except TelegramForbiddenError:
                log.info("user %s blocked the bot; risk alert skipped", user_id)
            except TelegramAPIError:
                log.exception("could not send risk alert to %s", user_id)
            await asyncio.sleep(0.05)
        return sent


async def risk_alert_loop(
    bot: Bot, session_pool: async_sessionmaker[AsyncSession]
) -> None:
    log.info("risk alert loop started")
    while True:
        try:
            await send_risk_alerts(bot, session_pool)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("risk alert loop failed")
        await asyncio.sleep(CHECK_EVERY)
