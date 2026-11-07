import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.constants import MAX_BOOK_NOTE_LENGTH, MAX_BOOK_PAGES
from BOOKzMA.handlers.common import offer_buddy_nudge, show
from BOOKzMA.repositories import books as books_repo
from BOOKzMA.repositories import users
from BOOKzMA.services.books import normalize_author, normalize_title
from BOOKzMA.services.reading_registration import register_reading
from BOOKzMA.services.reminder_cleanup import request_cleanup
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
BOOK_CALLBACK_RE = re.compile(
    r"book:(open|log|archive|archive_go|restore|set_pages):(\d{1,10})"
)
BOOK_NOTE_CALLBACK_RE = re.compile(r"book:note:(?:(edit|clear):)?(\d{1,10})")
BOOK_PAGE_RE = re.compile(r"books:p:(\d{1,15})")
BOOK_ARCHIVE_PAGE_RE = re.compile(r"books:archive:p:(\d{1,15})")


class AddBook(StatesGroup):
    waiting_for_title = State()
    waiting_for_author = State()
    waiting_for_total_pages = State()


class LogPages(StatesGroup):
    waiting_for_pages = State()


class SetBookPages(StatesGroup):
    waiting_for_total_pages = State()


class EditBookNote(StatesGroup):
    waiting_for_note = State()


BOOK_FORM_STATES = frozenset(
    state.state
    for state in (
        *AddBook.__all_states__,
        *LogPages.__all_states__,
        *SetBookPages.__all_states__,
        *EditBookNote.__all_states__,
    )
)


@router.message(
    F.chat.type != "private", F.text.in_({"📚 کتابخانه من", "📚 کتابخانهٔ من"})
)
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
    *,
    archived: bool = False,
) -> None:
    summary = await books_repo.shelf_summary(session, user_id)
    total = summary.archived_count if archived else summary.total_count - summary.archived_count
    last_page = max(0, (total - 1) // PAGE_SIZE)
    page = min(max(page, 0), last_page)
    items = await books_repo.list_visible(
        session, user_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE, archived=archived
    )
    await show(
        event,
        texts.bookshelf(
            summary.reading_count,
            total,
            archived=archived,
            finished=summary.finished_count,
            planned=summary.planned_count,
            unstarted=summary.unstarted_count,
            archived_count=summary.archived_count,
            total_count=summary.total_count,
            reading_titles=summary.reading_titles,
            page=page + 1,
            page_count=last_page + 1,
        ),
        keyboards.bookshelf_kb(
            [(item.book.id, item.book.title, item.book.status) for item in items],
            page=page,
            has_previous=page > 0,
            has_next=page < last_page,
            archived=archived,
            archived_count=summary.archived_count,
            can_add=True,
        ),
    )


async def render_book(
    event: Message | CallbackQuery,
    session: AsyncSession,
    user_id: int,
    book_id: int,
    settings: Settings | None = None,
) -> bool:
    progress = await books_repo.get_progress(session, user_id, book_id)
    if progress is None:
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
        _book_detail_keyboard(
            progress.book,
            settings,
        ),
    )
    return True


async def render_book_note(
    event: Message | CallbackQuery,
    session: AsyncSession,
    user_id: int,
    book_id: int,
) -> bool:
    progress = await books_repo.get_progress(session, user_id, book_id)
    if progress is None:
        return False
    await show(
        event,
        texts.book_note(progress.book.title, progress.book.note),
        keyboards.book_note_kb(book_id, progress.book.note is not None),
    )
    return True


def _book_detail_keyboard(book, settings: Settings | None):
    if settings is None:
        return keyboards.book_detail_with_pages_kb(
            book.id,
            book.status,
            has_page_count=book.total_pages is not None,
            has_note=book.note is not None,
        )
    catalog_message_id = book.catalog_message_id
    catalog_url = (
        f"https://t.me/{settings.channel_catalog_channel_username.lstrip('@')}"
        f"/{catalog_message_id}"
        if catalog_message_id is not None
        else None
    )
    return keyboards.book_detail_with_pages_kb(
            book.id,
            book.status,
            has_page_count=book.total_pages is not None,
            has_note=book.note is not None,
            catalog_message_id=catalog_message_id,
            catalog_url=catalog_url,
        )


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


@private_router.message(F.text.in_({"📚 کتابخانه من", "📚 کتابخانهٔ من"}))
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


@private_router.callback_query(F.data == "books:archive")
async def on_books_archive(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    await render_shelf(callback, session, callback.from_user.id, 0, archived=True)


@private_router.callback_query(F.data.startswith("books:archive:p:"))
async def on_books_archive_page(callback: CallbackQuery, session: AsyncSession) -> None:
    match = BOOK_ARCHIVE_PAGE_RE.fullmatch(callback.data or "")
    if match is None:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    await render_shelf(
        callback, session, callback.from_user.id, int(match[1]), archived=True
    )


@private_router.callback_query(F.data == "book:add")
async def on_add_book(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await users.get_or_create(
        session, callback.from_user.id, callback.from_user.username, callback.from_user.full_name
    )
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
    if book is None:
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_FLOW_LOST)
        return
    await session.commit()
    await state.clear()
    await message.answer(
        texts.book_added(book.title, book.total_pages),
        reply_markup=keyboards.book_detail_kb(book.id, book.status),
    )


@private_router.callback_query(F.data.startswith("book:open:"))
async def on_book_open(
    callback: CallbackQuery, session: AsyncSession, settings: Settings | None = None
) -> None:
    book_id = _callback_book_id(callback.data, "open")
    if book_id is None or not await render_book(
        callback, session, callback.from_user.id, book_id, settings
    ):
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    await callback.answer()


@private_router.callback_query(F.data.startswith("book:note:"))
async def on_book_note(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    match = BOOK_NOTE_CALLBACK_RE.fullmatch(callback.data or "")
    if match is None or int(match[2]) > 2_147_483_647:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    book_id = int(match[2])
    progress = await books_repo.get_progress(session, callback.from_user.id, book_id)
    if progress is None:
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    action = match[1]
    if action == "edit":
        await state.clear()
        await state.set_state(EditBookNote.waiting_for_note)
        await state.update_data(book_id=book_id)
        await callback.answer()
        await show(
            callback,
            texts.BOOK_ASK_NOTE,
            keyboards.book_note_cancel_kb(book_id),
        )
        return
    await state.clear()
    if action == "clear":
        if not await books_repo.set_note(session, callback.from_user.id, book_id, None):
            await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
            return
        await session.commit()
        await callback.answer(texts.BOOK_NOTE_CLEARED)
        await render_book_note(callback, session, callback.from_user.id, book_id)
        return
    await callback.answer()
    await render_book_note(callback, session, callback.from_user.id, book_id)


@form_router.message(
    EditBookNote.waiting_for_note, F.text, flags={"book_form_input": True}
)
async def on_book_note_text(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    note = (message.text or "").strip()
    if not note or len(note) > MAX_BOOK_NOTE_LENGTH:
        await message.answer(texts.BOOK_BAD_NOTE)
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    book_id = data.get("book_id")
    if not isinstance(book_id, int):
        await state.clear()
        await message.answer(texts.BOOK_FLOW_LOST)
        return
    if not await books_repo.set_note(session, message.from_user.id, book_id, note):
        await state.clear()
        await message.answer(texts.BOOK_NOT_FOUND)
        return
    await session.commit()
    await state.clear()
    await render_book_note(message, session, message.from_user.id, book_id)


@private_router.callback_query(F.data.startswith("book:log:"))
async def on_log_pages(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    book_id = _callback_book_id(callback.data, "log")
    progress = (
        await books_repo.get_progress(session, callback.from_user.id, book_id)
        if book_id is not None
        else None
    )
    if progress is None or progress.book.status in {"finished", "archived"}:
        await callback.answer(texts.BOOK_NOT_READABLE, show_alert=True)
        return
    if progress.book.total_pages is None:
        await callback.answer(texts.BOOK_PAGE_COUNT_MISSING, show_alert=True)
        return
    if progress.book.status != "reading":
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
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
    settings: Settings | None = None,
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
    await request_cleanup(bot, session, user.id, "reading", today)
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
        reply_markup=_book_detail_keyboard(result.progress.book, settings),
    )
    if registration.created:
        await offer_buddy_nudge(message, session, user)


@private_router.callback_query(F.data.startswith("book:set_pages:"))
async def on_set_book_pages(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    book_id = _callback_book_id(callback.data, "set_pages")
    progress = (
        await books_repo.get_progress(session, callback.from_user.id, book_id)
        if book_id is not None
        else None
    )
    if progress is None or progress.book.status not in {"planned", "reading"}:
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    if progress.book.total_pages is not None:
        await callback.answer(texts.BOOK_PAGE_COUNT_ALREADY_SET, show_alert=True)
        return
    await state.clear()
    await state.set_state(SetBookPages.waiting_for_total_pages)
    await state.update_data(book_id=book_id)
    await callback.answer()
    await show(callback, texts.BOOK_ASK_PAGE_COUNT_LATER, keyboards.books_cancel_kb())


@form_router.message(
    SetBookPages.waiting_for_total_pages, F.text, flags={"book_form_input": True}
)
async def on_set_book_total_pages(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    settings: Settings | None = None,
) -> None:
    total_pages = parse_positive_int(message.text or "", MAX_BOOK_PAGES)
    if total_pages is None:
        await message.answer(texts.BOOK_BAD_TOTAL_PAGES)
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    book_id = data.get("book_id")
    if not isinstance(book_id, int):
        await state.clear()
        await message.answer(texts.BOOK_FLOW_LOST)
        return
    result, progress = await books_repo.set_total_pages(
        session, message.from_user.id, book_id, total_pages
    )
    if result == "under_progress":
        await session.rollback()
        await message.answer(texts.BOOK_PAGE_COUNT_UNDER_PROGRESS)
        return
    if result == "already_set":
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_PAGE_COUNT_ALREADY_SET)
        return
    if result != "ok" or progress is None:
        await session.rollback()
        await state.clear()
        await message.answer(texts.BOOK_NOT_FOUND)
        return
    await session.commit()
    await state.clear()
    await message.answer(
        texts.book_detail(
            progress.book.title,
            progress.book.author,
            progress.pages_read,
            progress.book.total_pages,
            progress.book.status,
        ),
        reply_markup=_book_detail_keyboard(progress.book, settings),
    )


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


@private_router.callback_query(F.data.startswith("book:restore:"))
async def on_book_restore(
    callback: CallbackQuery, session: AsyncSession, settings: Settings | None = None
) -> None:
    book_id = _callback_book_id(callback.data, "restore")
    if book_id is None or not await books_repo.restore(
        session, callback.from_user.id, book_id
    ):
        await session.rollback()
        await callback.answer(texts.BOOK_NOT_FOUND, show_alert=True)
        return
    await session.commit()
    await callback.answer(texts.BOOK_RESTORED)
    await render_book(callback, session, callback.from_user.id, book_id, settings)
