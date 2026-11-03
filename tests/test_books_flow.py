import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import CallbackQuery, Chat, Document, InlineQuery, Message, Update, User

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.handlers import books, catalog, get_router, profile
from BOOKzMA.handlers.admin import NewBroadcast
from BOOKzMA.handlers.mesbak import SetReminderTime
from BOOKzMA.handlers.reminders import AddTime
from BOOKzMA.repositories.books import BookProgress, PageLogResult
from BOOKzMA.repositories.book_catalog import CatalogHit
from BOOKzMA.services.reading_registration import ReadingRegistration


@pytest.fixture(scope="module")
def dispatcher():
    root = get_router()

    class ObserveHandler(BaseMiddleware):
        async def __call__(self, handler, event, data):
            if data.get("capture_only"):
                return data["handler"].callback.__name__
            return await handler(event, data)

    root.message.middleware(ObserveHandler())
    root.callback_query.middleware(ObserveHandler())
    dp = Dispatcher(events_isolation=SimpleEventIsolation())
    dp.include_router(root)
    return dp


@pytest.fixture
def telegram(monkeypatch):
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    replies = AsyncMock()
    monkeypatch.setattr(Message, "answer", replies)
    monkeypatch.setattr(Message, "edit_text", AsyncMock())
    monkeypatch.setattr(CallbackQuery, "answer", AsyncMock())
    yield bot, replies
    asyncio.run(bot.session.close())


def message(text, *, message_id=101, group=False):
    return Message(
        message_id=message_id,
        date=datetime(2026, 10, 29, tzinfo=timezone.utc),
        chat=Chat(id=-100123 if group else 777, type="supergroup" if group else "private"),
        from_user=User(id=777, is_bot=False, first_name="Reader"),
        text=text,
    )


def callback(payload, *, group=False):
    return CallbackQuery(
        id="test-callback",
        from_user=message("").from_user,
        chat_instance="synthetic-chat",
        data=payload,
        message=message("screen", group=group),
    )


def session():
    return SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())


def book(book_id=1):
    return SimpleNamespace(
        id=book_id, title="Synthetic book", author=None, total_pages=100, status="reading"
    )


@pytest.mark.parametrize(
    "payload",
    [
        "books", "books:p:0", "book:add", "book:author_skip", "book:open:1",
        "book:log:1", "book:archive:1", "book:archive_go:1",
        "book:restore:1",
    ],
)
def test_group_book_callbacks_are_rejected_before_database_access(
    dispatcher, telegram, monkeypatch, payload
):
    bot, _ = telegram
    database_access = AsyncMock(side_effect=AssertionError("private data was queried"))
    for name in ("get_progress", "archive", "active_count", "visible_count"):
        monkeypatch.setattr(books.books_repo, name, database_access)
    monkeypatch.setattr(books.users, "get_or_create", database_access)

    async def run():
        await dispatcher.feed_update(
            bot, Update(update_id=1, callback_query=callback(payload, group=True)),
            session=session(),
        )
        CallbackQuery.answer.assert_awaited_once_with(texts.BOOK_PRIVATE_ONLY, show_alert=True)
        database_access.assert_not_awaited()

    asyncio.run(run())


@pytest.mark.parametrize("label", ["📚 کتابخانه من", "📚 کتابخانهٔ من"])
def test_group_library_menu_does_not_publish_the_shelf(
    dispatcher, telegram, monkeypatch, label
):
    bot, replies = telegram
    query = AsyncMock(side_effect=AssertionError("private data was queried"))
    monkeypatch.setattr(books.users, "get_or_create", query)

    async def run():
        await dispatcher.feed_update(
            bot, Update(update_id=1, message=message(label, group=True)),
            session=session(),
        )
        replies.assert_awaited_once_with(texts.BOOK_PRIVATE_ONLY)
        query.assert_not_awaited()

    asyncio.run(run())


def test_library_callback_without_a_chat_cannot_access_books(dispatcher, telegram):
    bot, _ = telegram

    async def run():
        inline = callback("book:open:1").model_copy(update={"message": None})
        await dispatcher.feed_update(bot, Update(update_id=1, callback_query=inline))
        CallbackQuery.answer.assert_awaited_once_with(texts.BOOK_PRIVATE_ONLY, show_alert=True)

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload,expected_page,archived",
    [("books:archive", 0, True), ("books:archive:p:3", 3, True)],
)
def test_archived_books_shelf_and_pagination_use_archive_query(
    dispatcher, telegram, monkeypatch, payload, expected_page, archived
):
    bot, _replies = telegram
    render = AsyncMock()
    monkeypatch.setattr(books, "render_shelf", render)

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback(payload)),
            session=session(),
        )
        render.assert_awaited_once_with(
            render.await_args.args[0],
            render.await_args.args[1],
            777,
            expected_page,
            archived=archived,
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    ("archived", "page", "expected_callback"),
    [
        (False, 0, "books:p:1"),
        (False, 1, "books:p:0"),
        (True, 0, "books:archive:p:1"),
        (True, 1, "books:archive:p:0"),
    ],
)
def test_shelf_paginates_nine_books_and_shows_page_number(
    monkeypatch, archived, page, expected_callback
):
    items = [
        SimpleNamespace(
            book=SimpleNamespace(id=index, title=f"Book {index}", status="reading")
        )
        for index in range(page * 8, min(page * 8 + 8, 9))
    ]
    list_visible = AsyncMock(return_value=items)
    show = AsyncMock()
    monkeypatch.setattr(books.books_repo, "list_visible", list_visible)
    monkeypatch.setattr(
        books.books_repo,
        "shelf_summary",
        AsyncMock(
            return_value=SimpleNamespace(
                total_count=9,
                archived_count=9 if archived else 0,
                reading_count=0,
                finished_count=0,
                planned_count=0,
                unstarted_count=9,
                reading_titles=(),
            )
        ),
    )
    monkeypatch.setattr(books, "show", show)

    async def run():
        await books.render_shelf(message("books"), session(), 777, page, archived=archived)

    asyncio.run(run())

    assert list_visible.await_args.kwargs == {
        "offset": page * 8,
        "limit": 8,
        "archived": archived,
    }
    rendered_text, markup = show.await_args.args[1:]
    current_page = "۲" if page else "۱"
    assert f"صفحه {current_page} از ۲" in rendered_text
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert expected_callback in callbacks


def test_archiving_book_does_not_record_reading_or_streak(dispatcher, telegram, monkeypatch):
    bot, _replies = telegram
    archive = AsyncMock(return_value=True)
    render = AsyncMock()
    register = AsyncMock()
    monkeypatch.setattr(books.books_repo, "archive", archive)
    monkeypatch.setattr(books, "render_shelf", render)
    monkeypatch.setattr(books, "register_reading", register)
    database = session()

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("book:archive_go:1")),
            session=database,
        )
        archive.assert_awaited_once_with(database, 777, 1)
        database.commit.assert_awaited_once()
        register.assert_not_awaited()

    asyncio.run(run())


def test_restore_archived_book_updates_status_and_renders_book(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    database = session()
    restore = AsyncMock(return_value=True)
    render = AsyncMock(return_value=True)
    monkeypatch.setattr(books.books_repo, "restore", restore)
    monkeypatch.setattr(books, "render_book", render)

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("book:restore:42")),
            session=database,
        )
        restore.assert_awaited_once_with(database, 777, 42)
        database.commit.assert_awaited_once()
        CallbackQuery.answer.assert_awaited_once_with(texts.BOOK_RESTORED)
        render.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "form_state", [AddTime.waiting, SetReminderTime.waiting, NewBroadcast.waiting_for_content]
)
def test_library_menu_can_leave_other_input_forms(
    dispatcher, telegram, monkeypatch, form_state
):
    bot, _ = telegram
    monkeypatch.setattr(
        books.users, "get_or_create", AsyncMock(return_value=SimpleNamespace(id=777))
    )
    shelf = AsyncMock()
    monkeypatch.setattr(books, "render_shelf", shelf)

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(form_state)
        await state.set_data({"old_input": "discard me"})
        await dispatcher.feed_update(
            bot, Update(update_id=1, message=message("📚 کتابخانهٔ من")), session=session()
        )
        shelf.assert_awaited_once()
        assert await state.get_state() is None
        assert await state.get_data() == {}

    asyncio.run(run())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("👤 پروفایل", "on_profile"), ("/profile", "on_profile"),
        ("⏰ یادآورها", "on_menu_reminders"), ("/reminders", "cmd_reminders"),
        ("🌍 منطقه زمانی", "on_menu_timezone"), ("/timezone", "cmd_timezone"),
        ("🤝 رفیق مطالعه", "on_menu_buddy"), ("💚 حمایت از پروژه", "on_support"),
    ],
)
def test_navigation_is_not_consumed_by_the_book_form(dispatcher, telegram, text, expected):
    bot, _ = telegram

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        for form_state in (*books.AddBook.__all_states__, *books.LogPages.__all_states__):
            await state.set_state(form_state)
            await state.set_data({"book_title": "Old title", "book_id": 1})
            handler = await dispatcher.feed_update(
                bot, Update(update_id=1, message=message(text)), capture_only=True
            )
            assert handler == expected
            assert await state.get_state() is None
            assert await state.get_data() == {}

    asyncio.run(run())


def test_unknown_command_is_not_saved_as_a_book_title(dispatcher, telegram):
    bot, _ = telegram

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.clear()
        await state.set_state(books.AddBook.waiting_for_title)
        await dispatcher.feed_update(
            bot, Update(update_id=1, message=message("/unknown")), capture_only=True
        )
        assert await state.get_data() == {}

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload", ["book:open:2", "books:p:0", "book:archive:1", "weekly", "tz", "read"]
)
def test_leaving_page_entry_discards_the_old_book(dispatcher, telegram, payload):
    bot, _ = telegram

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(books.LogPages.waiting_for_pages)
        await state.set_data({"book_id": 1})
        await dispatcher.feed_update(
            bot, Update(update_id=1, callback_query=callback(payload)), capture_only=True
        )
        assert await state.get_state() is None
        assert await state.get_data() == {}

    asyncio.run(run())


def test_opening_another_book_prevents_logging_to_the_old_one(
    dispatcher, telegram, monkeypatch
):
    bot, _ = telegram
    query = AsyncMock(return_value=BookProgress(book(2), 0))
    log = AsyncMock(side_effect=AssertionError("the previous book received a page count"))
    monkeypatch.setattr(books.books_repo, "get_progress", query)
    monkeypatch.setattr(books.books_repo, "log_pages", log)
    monkeypatch.setattr(
        books.users, "get_or_create",
        AsyncMock(return_value=SimpleNamespace(id=777, timezone="Asia/Tehran")),
    )

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(books.LogPages.waiting_for_pages)
        await state.set_data({"book_id": 1})
        await dispatcher.feed_update(
            bot, Update(update_id=1, callback_query=callback("book:open:2")), session=session()
        )
        await dispatcher.feed_update(
            bot, Update(update_id=2, message=message("10")), session=session()
        )
        log.assert_not_awaited()

    asyncio.run(run())


def test_concurrent_and_replayed_final_messages_create_one_book(
    dispatcher, telegram, monkeypatch
):
    bot, replies = telegram
    added = AsyncMock(return_value=("ok", book()))

    async def get_user(*args):
        await asyncio.sleep(0)
        return SimpleNamespace(id=777)

    monkeypatch.setattr(books.users, "get_or_create", get_user)
    monkeypatch.setattr(books.books_repo, "add", added)

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(books.AddBook.waiting_for_total_pages)
        await state.set_data({"book_title": "Synthetic book", "book_author": None})
        update = Update(update_id=10, message=message("100", message_id=301))
        await asyncio.gather(*(
            dispatcher.feed_update(bot, update, session=session()) for _ in range(2)
        ))
        await dispatcher.feed_update(bot, update, session=session())
        added.assert_awaited_once()
        replies.assert_awaited_once()
        assert await state.get_state() is None

    asyncio.run(run())


@pytest.mark.parametrize("author", [None, "  A & B  "])
def test_complete_add_book_flow_with_optional_author(dispatcher, telegram, monkeypatch, author):
    bot, replies = telegram
    monkeypatch.setattr(
        books.users, "get_or_create", AsyncMock(return_value=SimpleNamespace(id=777))
    )
    monkeypatch.setattr(books.books_repo, "active_count", AsyncMock(return_value=0))
    created = book()
    created.title = "A < B"
    add = AsyncMock(return_value=("ok", created))
    monkeypatch.setattr(books.books_repo, "add", add)
    register = AsyncMock()
    monkeypatch.setattr(books, "register_reading", register)
    db = session()

    async def send(event):
        if isinstance(event, CallbackQuery):
            update = Update(update_id=1, callback_query=event)
        else:
            update = Update(update_id=1, message=event)
        await dispatcher.feed_update(bot, update, session=db)

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.clear()
        await send(callback("book:add"))
        await send(message("  A   < B  "))
        assert (await state.get_data())["book_title"] == "A < B"
        await send(callback("book:author_skip") if author is None else message(author))
        assert await state.get_state() == books.AddBook.waiting_for_total_pages.state
        await send(message("0"))
        assert await state.get_state() == books.AddBook.waiting_for_total_pages.state
        add.assert_not_awaited()
        await send(message("۱۰۰"))
        add.assert_awaited_once_with(db, 777, "A < B", None if author is None else "A & B", 100)
        assert "A &lt; B" in replies.call_args.args[0]
        register.assert_not_awaited()
        assert await state.get_state() is None
        assert await state.get_data() == {}

    asyncio.run(run())


def test_over_remaining_pages_keeps_the_form_without_registering_reading(
    dispatcher, telegram, monkeypatch
):
    bot, replies = telegram
    monkeypatch.setattr(
        books.users, "get_or_create",
        AsyncMock(return_value=SimpleNamespace(id=777, timezone="Asia/Tehran")),
    )
    monkeypatch.setattr(
        books.books_repo, "log_pages",
        AsyncMock(return_value=PageLogResult("over", BookProgress(book(), 90))),
    )
    register = AsyncMock()
    monkeypatch.setattr(books, "register_reading", register)
    db = session()

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(books.LogPages.waiting_for_pages)
        await state.set_data({"book_id": 1})
        await dispatcher.feed_update(
            bot, Update(update_id=1, message=message("11")), session=db
        )
        register.assert_not_awaited()
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()
        assert await state.get_state() == books.LogPages.waiting_for_pages.state
        assert await state.get_data() == {"book_id": 1}
        replies.assert_awaited_once_with(texts.book_pages_over(10))

    asyncio.run(run())


def test_failed_database_commit_keeps_the_form_retryable(dispatcher, telegram, monkeypatch):
    bot, replies = telegram
    monkeypatch.setattr(
        books.users, "get_or_create", AsyncMock(return_value=SimpleNamespace(id=777))
    )
    monkeypatch.setattr(books.books_repo, "add", AsyncMock(return_value=("ok", book())))

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.set_state(books.AddBook.waiting_for_total_pages)
        await state.set_data({"book_title": "Synthetic book", "book_author": None})
        db = session()
        db.commit.side_effect = RuntimeError("synthetic transaction failure")
        with pytest.raises(RuntimeError, match="synthetic transaction failure"):
            await dispatcher.feed_update(
                bot, Update(update_id=1, message=message("100")), session=db
            )
        assert await state.get_state() == books.AddBook.waiting_for_total_pages.state
        replies.assert_not_awaited()

    asyncio.run(run())


def test_multiple_page_sessions_keep_progress_and_register_one_reading_day(
    dispatcher, telegram, monkeypatch
):
    bot, replies = telegram
    item = book()
    monkeypatch.setattr(
        books.users, "get_or_create",
        AsyncMock(return_value=SimpleNamespace(id=777, timezone="Asia/Tehran")),
    )
    monkeypatch.setattr(
        books.books_repo, "get_progress", AsyncMock(return_value=BookProgress(item, 0))
    )
    monkeypatch.setattr(
        books.books_repo, "log_pages", AsyncMock(side_effect=[
            PageLogResult("ok", BookProgress(item, 10)),
            PageLogResult("ok", BookProgress(item, 25)),
        ]),
    )
    register = AsyncMock(side_effect=[
        ReadingRegistration(True, 1, None, 0, None, ()),
        ReadingRegistration(False, 1, None, 0, None, ()),
    ])
    monkeypatch.setattr(books, "register_reading", register)
    nudge = AsyncMock()
    monkeypatch.setattr(books, "offer_buddy_nudge", nudge)

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.clear()
        for number, pages in enumerate((10, 15), start=1):
            await dispatcher.feed_update(
                bot, Update(update_id=number, callback_query=callback("book:log:1")),
                session=session(),
            )
            await dispatcher.feed_update(
                bot, Update(update_id=number + 10, message=message(str(pages), message_id=number)),
                session=session(),
            )
        assert register.await_count == 2
        nudge.assert_awaited_once()
        assert "۲۵ از ۱۰۰" in replies.call_args.args[0]
        assert texts.BOOK_STREAK_ALREADY_RECORDED in replies.call_args.args[0]
        assert await state.get_state() is None

    asyncio.run(run())


def test_catalog_search_is_private_and_paginates_results(dispatcher, telegram, monkeypatch):
    bot, replies = telegram
    database = session()
    search = AsyncMock(
        return_value=([CatalogHit(
            201, "برونرپوست@EppiccNURSE.pdf", None, "Document", None, 100, None
        )], True)
    )
    monkeypatch.setattr(catalog.book_catalog, "search", search)
    settings = Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        channel_catalog_db_path="/catalog/channel_data.db",
    )

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.clear()
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("catalog:search")),
            session=database,
            settings=settings,
        )
        await dispatcher.feed_update(
            bot,
            Update(update_id=2, message=message("  کتاب @BOOKzMA  ")),
            session=database,
            settings=settings,
        )
        search.assert_awaited_once_with(database, "کتاب", offset=0, limit=6)
        assert "نتیجه‌های ۱ تا ۱" in replies.call_args.args[0]
        assert "@EppiccNURSE" not in str(replies.call_args.kwargs["reply_markup"])
        assert await state.get_state() is None

    asyncio.run(run())


def test_catalog_inline_query_in_group_returns_post_link(dispatcher, telegram, monkeypatch):
    bot, _replies = telegram
    query = InlineQuery(
        id="inline-1",
        from_user=message("").from_user,
        query="کتاب",
        offset="",
    )
    answer = AsyncMock()
    monkeypatch.setattr(InlineQuery, "answer", answer)
    monkeypatch.setattr(
        catalog.book_catalog,
        "search",
        AsyncMock(
            return_value=(
                [CatalogHit(
                    201,
                    "برونرپوست@EppiccNURSE.pdf",
                    "caption",
                    "Document",
                    "application/pdf",
                    100,
                    None,
                )],
                False,
            )
        ),
    )
    settings = Settings(bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    settings.channel_catalog_db_path = "/catalog/channel_data.db"

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, inline_query=query),
            session=session(),
            settings=settings,
        )
        answer.assert_awaited_once()
        result = answer.call_args.args[0][0]
        assert result.title == "برونرپوست.pdf"
        assert "https://t.me/BOOKzMA/201" in result.input_message_content.message_text

    asyncio.run(run())


def test_catalog_search_is_disabled_without_source_path(dispatcher, telegram, monkeypatch):
    bot, _replies = telegram
    search = AsyncMock(side_effect=AssertionError("catalog query must be disabled"))
    monkeypatch.setattr(catalog.book_catalog, "search", search)
    settings = Settings(bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

    async def run():
        settings.channel_catalog_db_path = None
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("catalog:search")),
            session=session(),
            settings=settings,
        )
        CallbackQuery.answer.assert_awaited_once_with(
            texts.CATALOG_NOT_CONFIGURED, show_alert=True
        )
        search.assert_not_awaited()

    asyncio.run(run())


def test_catalog_result_uses_human_size_and_format_label():
    result = texts.catalog_result(
        "1984..جورج اورول.pdf",
        "📚۱۹۸۴ ✍️جورج اورول #۱۹۸۴ #جورج_اورول",
        4_913_989,
        "application/pdf",
    )
    assert "فرمت: pdf" in result
    assert "مگابایت" in result
    assert "application/pdf" not in result
    assert "6" in result or "۴.۷" in result


def test_catalog_download_falls_back_to_channel_link_when_copy_fails(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    monkeypatch.setattr(
        catalog.book_catalog,
        "get_entry",
        AsyncMock(
            return_value=SimpleNamespace(
                message_id=201,
                file_name="1984.pdf",
                caption_preview="caption",
                file_size=4_913_989,
                mime_type="application/pdf",
                bot_file_id=None,
            )
        ),
    )
    fail = AsyncMock(
        side_effect=TelegramBadRequest(
            method=None,
            message="BadRequest: message cannot be copied",
        )
    )
    monkeypatch.setattr(bot, "copy_message", fail)
    settings = Settings(bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    settings.channel_catalog_channel_username = "BOOKzMA"

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("catalog:download:201")),
            session=session(),
            settings=settings,
        )
        fail.assert_awaited_once()
        CallbackQuery.answer.assert_awaited_with(texts.CATALOG_FILE_FAILED, show_alert=True)

    asyncio.run(run())


def test_catalog_download_uses_cached_file_id_if_copy_fails(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    monkeypatch.setattr(
        catalog.book_catalog,
        "get_entry",
        AsyncMock(
            return_value=SimpleNamespace(
                message_id=201,
                file_name="@Blue_library درود.pdf",
                caption_preview="caption",
                file_size=1024,
                mime_type="application/pdf",
                bot_file_id="cached-document-id",
            )
        ),
    )
    monkeypatch.setattr(
        bot,
        "copy_message",
        AsyncMock(side_effect=TelegramBadRequest(method=None, message="copy unavailable")),
    )
    send_document = AsyncMock()
    monkeypatch.setattr(bot, "send_document", send_document)
    settings = Settings(bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    settings.channel_catalog_channel_username = "BOOKzMA"

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("catalog:download:201")),
            session=session(),
            settings=settings,
        )
        send_document.assert_awaited_once()
        assert send_document.await_args.kwargs["chat_id"] == 777
        assert send_document.await_args.kwargs["document"] == "cached-document-id"
        assert "@Blue_library" not in send_document.await_args.kwargs["caption"]

    asyncio.run(run())


def test_support_ticket_reaches_admin_and_admin_reply_reaches_user(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    admin_id = 999
    ticket_id = 900
    copied = AsyncMock(return_value=SimpleNamespace(message_id=555))
    sent = AsyncMock()
    monkeypatch.setattr(bot, "copy_message", copied)
    monkeypatch.setattr(bot, "send_message", sent)
    monkeypatch.setattr(
        profile.users,
        "get_or_create",
        AsyncMock(return_value=SimpleNamespace(id=777)),
    )
    monkeypatch.setattr(
        profile.support_repo, "is_blocked", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        profile.support_repo,
        "open_ticket",
        AsyncMock(return_value=SimpleNamespace(id=ticket_id)),
    )
    monkeypatch.setattr(
        profile.support_repo,
        "get_ticket",
        AsyncMock(return_value=SimpleNamespace(id=ticket_id, user_id=777, status="open")),
    )
    record_message = AsyncMock()
    monkeypatch.setattr(profile.support_repo, "record_message", record_message)
    settings = Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_telegram_ids=str(admin_id),
    )

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("support:ticket")),
            session=session(),
            settings=settings,
        )
        await dispatcher.feed_update(
            bot,
            Update(update_id=2, message=message("مشکل در دریافت کتاب")),
            session=session(),
            settings=settings,
        )
        copied.assert_awaited_once_with(
            chat_id=admin_id, from_chat_id=777, message_id=101
        )
        ticket = sent.await_args_list[0]
        assert ticket.kwargs["chat_id"] == admin_id
        assert ticket.kwargs["reply_to_message_id"] == 555
        assert ticket.kwargs["reply_markup"].inline_keyboard[0][0].callback_data == (
            "support:reply:900"
        )

        admin_user = User(id=admin_id, is_bot=False, first_name="Admin")
        admin_chat = Chat(id=admin_id, type="private")
        admin_screen = message("screen").model_copy(
            update={"chat": admin_chat, "from_user": admin_user}
        )
        admin_message = Message(
            message_id=201,
            date=datetime(2026, 11, 3, tzinfo=timezone.utc),
            chat=admin_chat,
            from_user=admin_user,
            text="پاسخ آماده است",
        )
        admin_callback = callback("support:reply:900").model_copy(
            update={"from_user": admin_user, "message": admin_screen}
        )
        await dispatcher.feed_update(
            bot,
            Update(update_id=3, callback_query=admin_callback),
            session=session(),
            settings=settings,
        )
        admin_state = dispatcher.fsm.get_context(bot=bot, chat_id=admin_id, user_id=admin_id)
        assert await admin_state.get_state() == profile.SupportReply.waiting_for_message.state
        admin_reply = admin_message.model_copy(
            update={"message_id": 202, "text": "مشکل برطرف شد."}
        )
        await dispatcher.feed_update(
            bot,
            Update(update_id=4, message=admin_reply),
            session=session(),
            settings=settings,
        )
        assert copied.await_count == 2
        assert copied.await_args.kwargs == {
            "chat_id": 777,
            "from_chat_id": admin_id,
            "message_id": 202,
            "reply_markup": keyboards.support_user_reply_kb(ticket_id),
        }
        assert record_message.await_count == 2
        assert record_message.await_args_list[1].args[1:] == (
            ticket_id,
            admin_id,
            "admin_reply",
        )
        user_reply_callback = callback("support:continue:900")
        await dispatcher.feed_update(
            bot,
            Update(update_id=5, callback_query=user_reply_callback),
            session=session(),
            settings=settings,
        )
        await dispatcher.feed_update(
            bot,
            Update(
                update_id=6,
                message=message("هنوز مشکل دارم", message_id=303),
            ),
            session=session(),
            settings=settings,
        )
        assert copied.await_count == 3
        assert copied.await_args.kwargs["message_id"] == 303
        assert sent.await_count == 2
        assert record_message.await_count == 3

    asyncio.run(run())


def test_support_ticket_is_private_only(dispatcher, telegram):
    bot, _replies = telegram

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("support:ticket", group=True)),
        )
        CallbackQuery.answer.assert_awaited_once_with(texts.BOOK_PRIVATE_ONLY, show_alert=True)

    asyncio.run(run())


def test_support_block_requires_admin_and_blocks_ticket_creation(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    toggle = AsyncMock(return_value=True)
    edit_markup = AsyncMock()
    monkeypatch.setattr(Message, "edit_reply_markup", edit_markup)
    monkeypatch.setattr(profile.support_repo, "toggle_block", toggle)
    monkeypatch.setattr(
        profile.support_repo,
        "get_ticket",
        AsyncMock(return_value=SimpleNamespace(id=900, user_id=777, status="open")),
    )
    settings = Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_telegram_ids="999",
    )

    async def run():
        unauthorized = callback("support:block:900")
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=unauthorized),
            session=session(),
            settings=settings,
        )
        CallbackQuery.answer.assert_awaited_once_with(
            texts.SUPPORT_REPLY_UNAUTHORIZED, show_alert=True
        )
        toggle.assert_not_awaited()

        admin_id = 999
        admin_user = User(id=admin_id, is_bot=False, first_name="Admin")
        admin_chat = Chat(id=admin_id, type="private")
        admin_message = message("ticket").model_copy(update={"chat": admin_chat})
        admin_callback = callback("support:block:900").model_copy(
            update={"from_user": admin_user, "message": admin_message}
        )
        admin_session = session()
        await dispatcher.feed_update(
            bot,
            Update(update_id=2, callback_query=admin_callback),
            session=admin_session,
            settings=settings,
        )
        toggle.assert_awaited_once_with(admin_session, 777, admin_id)
        edit_markup.assert_awaited_once_with(
            reply_markup=keyboards.support_reply_kb(900, 777, True)
        )

        monkeypatch.setattr(
            profile.support_repo, "is_blocked", AsyncMock(return_value=True)
        )
        monkeypatch.setattr(
            profile.users,
            "get_or_create",
            AsyncMock(return_value=SimpleNamespace(id=777)),
        )
        blocked_callback = callback("support:ticket")
        await dispatcher.feed_update(
            bot,
            Update(update_id=3, callback_query=blocked_callback),
            session=session(),
            settings=settings,
        )
        CallbackQuery.answer.assert_awaited_with(texts.SUPPORT_USER_BLOCKED, show_alert=True)
        assert await dispatcher.fsm.get_context(
            bot=bot, chat_id=777, user_id=777
        ).get_state() is None

    asyncio.run(run())


def test_channel_post_ingestion_indexes_only_configured_channel(dispatcher, telegram, monkeypatch):
    bot, _replies = telegram
    upsert = AsyncMock()
    monkeypatch.setattr(catalog.book_catalog, "upsert_batch", upsert)
    channel_chat = Chat(
        id=-100123,
        type="channel",
        title="BOOKzMA",
        username="BOOKzMA",
    )
    post = Message(
        message_id=501,
        date=datetime(2026, 11, 3, tzinfo=timezone.utc),
        chat=channel_chat,
        caption="کتاب آزمایشی @BOOKzMA",
        document=Document(
            file_id="bot-file-id",
            file_unique_id="unique-file-id",
            file_name="کتاب.pdf",
            mime_type="application/pdf",
            file_size=1024,
        ),
    )
    settings = Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        channel_catalog_db_path="/catalog/channel_data.db",
    )
    database = session()

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, channel_post=post),
            session=database,
            settings=settings,
        )
        values = upsert.await_args.args[1][0]
        assert values["message_id"] == 501
        assert values["source_row_id"] == -501
        assert values["bot_file_id"] == "bot-file-id"
        assert "bookzma" not in values["search_text"]
        assert "raw_data" not in values
        database.commit.assert_awaited_once()

    asyncio.run(run())


def test_catalog_add_creates_personal_book_without_page_count(
    dispatcher, telegram, monkeypatch
):
    bot, _replies = telegram
    created = book()
    created.total_pages = None
    created.catalog_message_id = 201
    created.status = "planned"
    monkeypatch.setattr(
        catalog.book_catalog,
        "get_entry",
        AsyncMock(
            return_value=SimpleNamespace(
                message_id=201,
                file_name="Book title.pdf",
                caption_preview=None,
                media_type="Document",
            )
        ),
    )
    monkeypatch.setattr(
        catalog.users, "get_or_create", AsyncMock(return_value=SimpleNamespace(id=777))
    )
    add = AsyncMock(return_value=("ok", created))
    monkeypatch.setattr(catalog.books_repo, "add", add)
    database = session()
    settings = Settings(
        bot_token="123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        channel_catalog_channel_username="BOOKzMA",
    )

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("catalog:add:201")),
            session=database,
            settings=settings,
        )
        add.assert_awaited_once_with(
            database, 777, "Book title", None, None, catalog_message_id=201
        )
        database.commit.assert_awaited_once()
        markup = Message.edit_text.await_args.kwargs["reply_markup"]
        buttons = [button for row in markup.inline_keyboard for button in row]
        assert any(button.callback_data == "catalog:download:201" for button in buttons)
        assert any(button.url == "https://t.me/BOOKzMA/201" for button in buttons)

    asyncio.run(run())


def test_book_page_logging_requires_a_total_page_count(dispatcher, telegram, monkeypatch):
    bot, _replies = telegram
    item = book()
    item.total_pages = None
    item.status = "planned"
    monkeypatch.setattr(
        books.books_repo,
        "get_progress",
        AsyncMock(return_value=BookProgress(item, 0)),
    )

    async def run():
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("book:log:1")),
            session=session(),
        )
        CallbackQuery.answer.assert_awaited_once_with(
            texts.BOOK_PAGE_COUNT_MISSING, show_alert=True
        )

    asyncio.run(run())


def test_catalog_book_can_set_page_count_later(dispatcher, telegram, monkeypatch):
    bot, replies = telegram
    item = book()
    item.total_pages = None
    item.status = "planned"
    updated = BookProgress(item, 0)
    monkeypatch.setattr(
        books.books_repo, "get_progress", AsyncMock(return_value=updated)
    )
    set_pages = AsyncMock(return_value=("ok", updated))
    monkeypatch.setattr(books.books_repo, "set_total_pages", set_pages)
    register = AsyncMock()
    monkeypatch.setattr(books, "register_reading", register)
    database = session()

    async def run():
        state = dispatcher.fsm.get_context(bot=bot, chat_id=777, user_id=777)
        await state.clear()
        await dispatcher.feed_update(
            bot,
            Update(update_id=1, callback_query=callback("book:set_pages:1")),
            session=database,
        )
        assert await state.get_state() == books.SetBookPages.waiting_for_total_pages.state
        await dispatcher.feed_update(
            bot,
            Update(update_id=2, message=message("۱۰۰")),
            session=database,
        )
        set_pages.assert_awaited_once_with(database, 777, 1, 100)
        database.commit.assert_awaited_once()
        assert await state.get_state() is None
        assert "Synthetic book" in replies.call_args.args[0]
        register.assert_not_awaited()

    asyncio.run(run())
