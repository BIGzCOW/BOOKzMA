from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import texts
from BOOKzMA.handlers.common import offer_buddy_nudge, render_home
from BOOKzMA.repositories import users
from BOOKzMA.services.reading_registration import register_reading
from BOOKzMA.utils import local_today

router = Router()


@router.callback_query(F.data == "read")
async def on_read(callback: CallbackQuery, session: AsyncSession) -> None:
    tg = callback.from_user
    user = await users.get_or_create(session, tg.id, tg.username, tg.full_name)
    today = local_today(user.timezone)
    registration = await register_reading(session, user, today)
    await session.commit()

    toast = texts.read_toast(
        registration.streak,
        registration.created,
        freeze_used=(
            registration.freeze_change is not None
            and registration.freeze_change.used_day is not None
        ),
        freeze_earned=(
            registration.freeze_change is not None and registration.freeze_change.earned
        ),
        freeze_balance=registration.freeze_balance,
        comeback=texts.comeback_line(
            registration.comeback_change, registration.streak
        ),
        badges=list(registration.badges),
    )
    await callback.answer(toast)
    await render_home(callback, session, tg)
    if registration.created:
        await offer_buddy_nudge(
            callback.message if isinstance(callback.message, Message) else None,
            session,
            user,
        )
