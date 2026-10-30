import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeChat

from BOOKzMA.config import Settings
from BOOKzMA.handlers import get_router
from BOOKzMA.middlewares.db import DbSessionMiddleware
from BOOKzMA.middlewares.membership import MembershipMiddleware
from BOOKzMA.middlewares.rate_limit import RateLimitMiddleware
from BOOKzMA.services.scheduler import reminder_loop
from BOOKzMA.services.mesbak_scheduler import mesbak_reminder_loop
from BOOKzMA.services.broadcast import broadcast_loop
from BOOKzMA.services.risk_alert import risk_alert_loop

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="منوی اصلی و استریک"),
    BotCommand(command="reminders", description="یادآورهای مطالعه"),
    BotCommand(command="timezone", description="منطقه زمانی"),
    BotCommand(command="profile", description="پروفایل و استریک من"),
    BotCommand(command="mesbak", description="استریک و یادآوری مسباک"),
    BotCommand(command="support", description="حمایت از پروژه"),
]
ADMIN_COMMANDS = [*COMMANDS, BotCommand(command="admin", description="مدیریت ربات")]


async def start_bot(
    settings: Settings,
    session_pool,
    bot_session: BaseSession | None = None,
) -> tuple[Bot, list[asyncio.Task]]:
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=bot_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Read FSM state only after the previous update for this user/chat finishes.
    dp = Dispatcher(events_isolation=SimpleEventIsolation())
    membership = MembershipMiddleware(settings.admin_ids)
    rate_limit = RateLimitMiddleware(
        settings.rate_limit_max_updates,
        settings.rate_limit_window_seconds,
        settings.admin_ids,
    )
    dp.update.outer_middleware(DbSessionMiddleware(session_pool))
    # لایمیت ارزان‌ترین گیت است و باید قبل از بقیه اجرا شود؛ روی آپدیتِ مسدودشده
    # نه هندلر اجرا می‌شود نه session باز می‌شود.
    dp.message.outer_middleware(rate_limit)
    dp.callback_query.outer_middleware(rate_limit)
    dp.message.outer_middleware(membership)
    dp.callback_query.outer_middleware(membership)
    dp.workflow_data["settings"] = settings
    dp.include_router(get_router())

    reminders_task = asyncio.create_task(reminder_loop(bot, session_pool))
    mesbak_task = asyncio.create_task(mesbak_reminder_loop(bot, session_pool))
    broadcast_task = asyncio.create_task(broadcast_loop(bot, session_pool))
    risk_alert_task = asyncio.create_task(risk_alert_loop(bot, session_pool))
    try:
        await bot.set_my_commands(COMMANDS)
        for admin_id in settings.admin_ids:
            await bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
    except TelegramAPIError as exc:
        log.warning("set_my_commands failed (%s), continuing", type(exc).__name__)
    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    log.info("Telegram polling task started")
    return bot, [reminders_task, mesbak_task, broadcast_task, risk_alert_task, polling_task]
