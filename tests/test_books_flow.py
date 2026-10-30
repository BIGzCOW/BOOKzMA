import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from BOOKzMA import texts
from BOOKzMA.handlers import books, get_router
from BOOKzMA.handlers.admin import NewBroadcast
from BOOKzMA.handlers.mesbak import SetReminderTime
from BOOKzMA.handlers.reminders import AddTime
from BOOKzMA.repositories.books import BookProgress, PageLogResult
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


def test_group_library_menu_does_not_publish_the_shelf(dispatcher, telegram, monkeypatch):
    bot, replies = telegram
    query = AsyncMock(side_effect=AssertionError("private data was queried"))
    monkeypatch.setattr(books.users, "get_or_create", query)

    async def run():
        await dispatcher.feed_update(
            bot, Update(update_id=1, message=message("📚 کتابخانهٔ من", group=True)),
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
