import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA.repositories import broadcasts, users

log = logging.getLogger(__name__)
SEND_INTERVAL = 0.2
MAX_ATTEMPTS = 3
CHECK_INTERVAL = 1


async def broadcast_loop(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> None:
    async with session_pool() as session:
        await broadcasts.recover_inflight(session)
        await session.commit()
    while True:
        try:
            if await send_one(bot, session_pool):
                await asyncio.sleep(SEND_INTERVAL)
            else:
                await asyncio.sleep(CHECK_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("broadcast worker failed")
            await asyncio.sleep(CHECK_INTERVAL)


async def send_one(bot: Bot, session_pool: async_sessionmaker[AsyncSession]) -> bool:
    async with session_pool() as session:
        item = await broadcasts.next_delivery(session)
        if item is None:
            await broadcasts.complete_finished_campaigns(session)
            await session.commit()
            return False
        campaign, delivery = item
        if not await broadcasts.eligible_recipient(session, campaign, delivery.user_id):
            await broadcasts.set_delivery_state(
                session, delivery.id, "cancelled", "audience_inactive"
            )
            await session.commit()
            return True
        await broadcasts.set_delivery_state(session, delivery.id, "sending")
        delivery.attempts += 1
        await session.commit()

    reply_markup = None
    if campaign.button_label and campaign.button_url:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=campaign.button_label, url=campaign.button_url)]
            ]
        )
    try:
        if campaign.media_type == "photo":
            await bot.send_photo(
                delivery.user_id,
                campaign.media_file_id,
                caption=campaign.text or None,
                reply_markup=reply_markup,
                parse_mode=None,
            )
        elif campaign.media_type == "video":
            await bot.send_video(
                delivery.user_id,
                campaign.media_file_id,
                caption=campaign.text or None,
                reply_markup=reply_markup,
                parse_mode=None,
            )
        else:
            await bot.send_message(
                delivery.user_id,
                campaign.text,
                reply_markup=reply_markup,
                parse_mode=None,
            )
    except TelegramRetryAfter as error:
        async with session_pool() as session:
            state = "pending" if delivery.attempts < MAX_ATTEMPTS else "failed"
            next_attempt = datetime.now(timezone.utc) + timedelta(seconds=error.retry_after)
            await broadcasts.set_delivery_state(
                session,
                delivery.id,
                state,
                "retry_after",
                next_attempt if state == "pending" else None,
            )
            await session.commit()
    except (TelegramNetworkError, TelegramServerError):
        async with session_pool() as session:
            state = "pending" if delivery.attempts < MAX_ATTEMPTS else "failed"
            delay = min(2**delivery.attempts, 30)
            next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)
            await broadcasts.set_delivery_state(
                session,
                delivery.id,
                state,
                "temporary_error",
                next_attempt if state == "pending" else None,
            )
            await session.commit()
    except TelegramForbiddenError:
        async with session_pool() as session:
            await users.mark_broadcast_unavailable(session, delivery.user_id)
            await broadcasts.set_delivery_state(session, delivery.id, "failed", "forbidden")
            await session.commit()
    except TelegramAPIError:
        async with session_pool() as session:
            await broadcasts.set_delivery_state(session, delivery.id, "failed", "telegram_error")
            await session.commit()
    else:
        async with session_pool() as session:
            await broadcasts.set_delivery_state(session, delivery.id, "sent")
            await session.commit()
    return True