from aiogram import Router

from BOOKzMA.middlewares.book_flow import BookFlowNavigationMiddleware
from BOOKzMA.handlers import (
    account,
    admin,
    books,
    buddy,
    onboarding,
    mesbak,
    mesbak_social,
    profile,
    reminders,
    start,
    streak,
    timezone,
    weekly,
)


def get_router() -> Router:
    # فیچر جدید = یه فایل تو همین پوشه + یه خط اینجا
    router = Router()
    book_navigation = BookFlowNavigationMiddleware(books.BOOK_FORM_STATES)
    router.message.middleware(book_navigation)
    router.callback_query.middleware(book_navigation)
    router.include_routers(
        start.router,
        books.router,
        onboarding.router,
        mesbak.router,
        mesbak_social.router,
        admin.router,
        account.router,
        buddy.router,
        profile.router,
        streak.router,
        reminders.router,
        timezone.router,
        weekly.router,
        books.form_router,
    )
    return router
