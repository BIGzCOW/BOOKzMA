import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.constants import MAX_ACTIVE_BOOKS, MAX_BOOK_PAGES
from BOOKzMA.handlers.common import offer_buddy_nudge, show
from BOOKzMA.repositories import books as books_repo
from BOOKzMA.repositories import users
from BOOKzMA.services.books import normalize_author, normalize_title
from BOOKzMA.services.reading_registration import register_reading
from BOOKzMA.utils import local_today, parse_positive_int

router = Router()
# Navigation precedes other forms; book text inputs follow all existing menus.
private_router = Router()
private_router.message.filter(F.chat.type == "private")
private_router.callback_query.filter(F.message.chat.type == "private")
router.include_router(private_router)
form_router = Router()
form_router.message.filter(F.chat.type == "private", ~F.text.startswith("/"))
form_router.callback_query.filter(F.message.chat.type == "private")
PAGE_SIZE = 8
BOOK_CALLBACK_RE = re.compile(r"book:(open|log|archive|archive_go):(\d{1,10})")
BOOK_PAGE_RE = re.compile(r"books:p:(\d{1,6})")


class AddBook(StatesGroup):
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_total_pages = State()


class LogPages(StatesGroup):
    waiting_for_pages = State()


BOOK_FORM_STATES = frozenset(
    state.state for state in (*AddBook.__all_states__, *LogPages.__all_states__)
)


@router.message(F.chat.type != "private", F.text == "📚 کتابخانهٔ من")
async def on_group_books(message: Message) -> None:
    await message.answer(texts.BOOK_PRIVATE_ONLY)


@router.callback_query(
    lambda callback: (
        not isinstance(callback.message, Message) or callback.message.chat.type != "private"
    ),
    (F.data == "books") | F.data.startswith("books:") | F.data.startswith("book:"),
)
async def on_group_book_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.BOOK_PRIVATE_ONLY, show_alert=True)


def _callback_book_id(data: str | None, action: str) -> int | None:
    match = BOOK_CALLBACK_RE.fullmatch(data or "")
    if match is None or match[1] != action:
        return None
    value = int(match[2])
    return value if value <= 2_147_483_647 else None


async def render_shelf(
    event: Message | CallbackQuery,
    session: AsyncSession,
    user_id: int,
    page: int = 0,
) -> None:
    total = await books_repo.visible_count(session, user_id)
    last_page = max(0, (total - 1) // PAGE_SIZE)
    page = min(max(page, 0), last_page)
    items = await books_repo.list_visible(
        session, user_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE
    )
    active = await books_repo.active_count(session, user_id)
    await show(
        event,
        texts.bookshelf(active, total),
        keyboards.bookshelf_kb(
            [(item.book.id, item.book.title, item.book.status) for item in items],
            page=page,
            has_previous=page > 0,
            has_next=page < last_page,
            can_add=active < MAX_ACTIVE_BOOKS,
        ),
    )


async def render_book(
    event: Message | CallbackQuery,
    session: AsyncSession,
    user_id: int,
    book_id: int,
) -> bool:
    progress = await books_repo.get_progress(session, user_id, book_id)
    if progress is None or progress.book.status == "archived":
        return False
    await show(
        event,
        texts.book_detail(
            progress.book.title,
            progress.book.author,
            progress.pages_read,
            progress.book.total_pages,
            progress.book.status,
        ),
        keyboards.book_detail_kb(progress.book.id, progress.book.status),
    )
    return True


@private_router.callback_query(F.data == "books")
async def on_books(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    await session.commit()
    await render_shelf(callback, session, user.id)


@private_router.message(F.text == "📚 کتابخانهٔ من")
async def on_books_menu(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    user = await users.get_or_create(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    await session.commit()
    await render_shelf(message, session, user.id)


@private_router.callback_query(F.data.startswith("books:p:"))
async def on_books_page(callback: CallbackQuery, session: AsyncSession) -> None:
    match = BOOK_PAGE_RE.fullmatch(callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    await render_shelf(callback, session, callback.from_user.id, int(match[1]))


@private_router.callback_query(F.data == "book:add")
async def on_add_book(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    if await books_repo.active_count(session, user.id) >= MAX_ACTIVE_BOOKS:
        await session.commit()
        await callback.answer(texts.BOOK_LIMIT, show_alert=True)
        return
    await session.commit()
    await state.set_state(AddBook.waiting_for_title)
    await callback.answer()
    await show(callback, texts.BOOK_ASK_TITLE, keyboards.books_cancel_kb())


@form_router.message(AddBook.waiting_for_title, F.text, flags={"book_form_input": True})
async def on_book_title(message: Message, state: FSMContext) -> None:
    title = normalize_title(message.text or "")
    if title is None:
        await message.answer(texts.BOOK_BAD_TITLE)
        return
    await state.update_data(book_title=title)
    await state.set_state(AddBook.waiting_for_author)
    await message.answer(texts.BOOK_ASK_AUTHOR, reply_markup=keyboards.book_author_kb())


@form_router.message(AddBook.waiting_for_author, F.text, flags={"book_form_input": True})
async def on_book_author(message: Message, state: FSMContext) -> None:
    author = normalize_author(message.text or "")
    if author is None:
        await message.answer(texts.BOOK_BAD_AUTHOR)
        return
    await state.update_data(book_author=author)
    await state.set_state(AddBook.waiting_for_total_pages)
    await message.answer(texts.BOOK_ASK_TOTAL_PAGES, reply_markup=keyboards.books_cancel_kb())


@form_router.callback_query(
    AddBook.waiting_for_author, F.data == "book:author_skip", flags={"book_form_input": True}
)
async def on_book_author_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(book_author=None)
    await state.set_state(AddBook.waiting_for_total_pages)
    await callback.answer()
    await show(callback, texts.BOOK_ASK_TOTAL_PAGES, keyboards.books_cancel_kb())


@form_router.message(AddBook.waiting_for_total_pages, F.text, flags={"book_form_input": True})
async def on_book_total_pages(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    total_pages = parse_positive_int(message.text or "", MAX_BOOK_PAGES)
    if total_pages is None:
        await message.answer(texts.BOOK_BAD_TOTAL_PAGES)
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    title = data.get("book_title")
    author = data.get("book_author")
    if not isinstance(title, str) or (author is not None and not isinstance(author, str)):
        await state.clear()
        await message.answer(texts.BOOK_FLOW_LOST)
        return
    user = await users.get_or_create(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    result, book = await books_repo.add(session, user.id, title, author, total_pages)
    if result == "limit" or book is None:
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_LIMIT)
        return
    await session.commit()
    await state.clear()
    await message.answer(
        texts.book_added(book.title, book.total_pages),
        reply_markup=keyboards.book_detail_kb(book.id, book.status),
    )


@private_router.callback_query(F.data.startswith("book:open:"))
async def on_book_open(callback: CallbackQuery, session: AsyncSession) -> None:
    book_id = _callback_book_id(callback.data, "open")
    if book_id is None or not await render_book(
        callback, session, callback.from_user.id, book_id
    ):
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    await callback.answer()


@private_router.callback_query(F.data.startswith("book:log:"))
async def on_log_pages(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    book_id = _callback_book_id(callback.data, "log")
    progress = (
        await books_repo.get_progress(session, callback.from_user.id, book_id)
        if book_id is not None
        else None
    )
    if progress is None or progress.book.status != "reading":
        await callback.answer(texts.BOOK_NOT_READABLE, show_alert=True)
        return
    await state.set_state(LogPages.waiting_for_pages)
    await state.update_data(book_id=book_id)
    await callback.answer()
    await show(
        callback,
        texts.book_ask_pages(progress.book.title, progress.book.total_pages - progress.pages_read),
        keyboards.books_cancel_kb(),
    )


@form_router.message(LogPages.waiting_for_pages, F.text, flags={"book_form_input": True})
async def on_pages_read(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    pages = parse_positive_int(message.text or "", MAX_BOOK_PAGES)
    if pages is None:
        await message.answer(texts.BOOK_BAD_PAGES)
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    book_id = data.get("book_id")
    if not isinstance(book_id, int):
        await state.clear()
        await message.answer(texts.BOOK_FLOW_LOST)
        return
    user = await users.get_or_create(
        session,
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    today = local_today(user.timezone)
    result = await books_repo.log_pages(
        session, user.id, book_id, today, pages, message.message_id
    )
    if result.status == "over" and result.progress is not None:
        remaining = result.progress.book.total_pages - result.progress.pages_read
        await session.rollback()
        await message.answer(texts.book_pages_over(remaining))
        return
    if result.status == "duplicate" and result.progress is not None:
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_PAGES_DUPLICATE)
        return
    if result.status != "ok" or result.progress is None:
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_NOT_READABLE)
        return

    registration = await register_reading(session, user, today)
    await session.commit()
    await state.clear()
    reading_message = (
        texts.read_toast(
            registration.streak,
            True,
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
        if registration.created
        else texts.BOOK_STREAK_ALREADY_RECORDED
    )
    await message.answer(
        texts.pages_logged(
            result.progress.book.title,
            pages,
            result.progress.pages_read,
            result.progress.book.total_pages,
            result.progress.book.status == "finished",
            reading_message,
        ),
        reply_markup=keyboards.book_detail_kb(
            result.progress.book.id, result.progress.book.status
        ),
    )
    if registration.created:
        await offer_buddy_nudge(message, session, user)


@private_router.callback_query(F.data.startswith("book:archive:"))
async def on_book_archive_ask(callback: CallbackQuery, session: AsyncSession) -> None:
    book_id = _callback_book_id(callback.data, "archive")
    progress = (
        await books_repo.get_progress(session, callback.from_user.id, book_id)
        if book_id is not None
        else None
    )
    if progress is None or progress.book.status == "archived":
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    await callback.answer()
    await show(
        callback,
        texts.book_archive_confirm(progress.book.title),
        keyboards.book_archive_confirm_kb(progress.book.id),
    )


@private_router.callback_query(F.data.startswith("book:archive_go:"))
async def on_book_archive(callback: CallbackQuery, session: AsyncSession) -> None:
    book_id = _callback_book_id(callback.data, "archive_go")
    if book_id is None or not await books_repo.archive(
        session, callback.from_user.id, book_id
    ):
        await session.rollback()
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    await session.commit()
    await callback.answer(texts.BOOK_ARCHIVED)
    await render_shelf(callback, session, callback.from_user.id)
