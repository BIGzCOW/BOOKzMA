import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Animation,
    Audio,
    CallbackQuery,
    Document,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InputTextMessageContent,
    Message,
    PhotoSize,
    Sticker,
    Video,
    VideoNote,
    Voice,
)
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA import keyboards, texts
from BOOKzMA.config import Settings
from BOOKzMA.constants import MAX_BOOK_TITLE_LENGTH
from BOOKzMA.handlers.common import show
from BOOKzMA.repositories import book_catalog, books as books_repo, users
from BOOKzMA.services.catalog_text import (
    clean_caption,
    normalize_catalog_text,
    strip_channel_handles,
)

log = logging.getLogger(__name__)
router = Router()
private_router = Router()
private_router.message.filter(F.chat.type == "private")
private_router.callback_query.filter(F.message.chat.type == "private")
router.include_router(private_router)

CATALOG_PAGE_SIZE = 6
CATALOG_MESSAGE_RE = re.compile(r"catalog:(open|add|download):(\d{1,20})")
CATALOG_PAGE_RE = re.compile(r"catalog:p:(\d{1,6})")
MAX_INLINE_OFFSET = 100_000


class SearchCatalog(StatesGroup):
    waiting_for_query = State()


SEARCH_FORM_STATES = frozenset(state.state for state in SearchCatalog.__all_states__)


@router.callback_query(
    lambda callback: (
        not isinstance(callback.message, Message) or callback.message.chat.type != "private"
    ),
    F.data.startswith("catalog:"),
)
async def on_group_catalog_callback(callback: CallbackQuery) -> None:
    await callback.answer(texts.BOOK_PRIVATE_ONLY, show_alert=True)

def _message_media(
    message: Message,
) -> tuple[str | None, int | None, str | None, str, str | None] | None:
    media: Document | Audio | Animation | Video | VideoNote | Voice | Sticker | PhotoSize | None
    media_type: str
    if message.document is not None:
        media, media_type = message.document, "Document"
    elif message.photo:
        media, media_type = message.photo[-1], "photo"
    elif message.video is not None:
        media, media_type = message.video, "video"
    elif message.audio is not None:
        media, media_type = message.audio, "audio"
    elif message.animation is not None:
        media, media_type = message.animation, "animation"
    elif message.voice is not None:
        media, media_type = message.voice, "voice"
    elif message.video_note is not None:
        media, media_type = message.video_note, "video_note"
    elif message.sticker is not None:
        media, media_type = message.sticker, "sticker"
    else:
        return None

    file_name = getattr(media, "file_name", None)
    file_size = getattr(media, "file_size", None)
    mime_type = getattr(media, "mime_type", None)
    bot_file_id = media.file_id if media_type == "Document" else None
    return file_name, file_size, mime_type, media_type, bot_file_id


@router.channel_post()
async def on_main_channel_media(
    message: Message, session: AsyncSession, settings: Settings
) -> None:
    username = message.chat.username
    media = _message_media(message)
    if (
        settings.channel_catalog_db_path is None
        or not username
        or username.casefold() != settings.channel_catalog_channel_username.lstrip("@").casefold()
        or media is None
    ):
        return
    file_name, file_size, mime_type, media_type, bot_file_id = media
    _display, caption_preview, caption_search = clean_caption(
        message.caption, settings.channel_catalog_channel_username
    )
    search_text = normalize_catalog_text(
        f"{file_name or ''} {caption_search}"
    )[:6000]
    await book_catalog.upsert_batch(
        session,
        [
            {
                "message_id": message.message_id,
                "source_row_id": -message.message_id,
                "file_name": file_name,
                "caption_preview": caption_preview or None,
                "caption_search": caption_search,
                "search_text": search_text,
                "media_type": media_type,
                "mime_type": mime_type,
                "file_size": file_size,
                "posted_at": message.date.isoformat(),
                "bot_file_id": bot_file_id,
            }
        ],
        next_source_row_id=-message.message_id,
    )
    await session.commit()



def _catalog_message_id(data: str | None, action: str) -> int | None:
    match = CATALOG_MESSAGE_RE.fullmatch(data or "")
    if match is None or match[1] != action:
        return None
    message_id = int(match[2])
    return message_id if 0 < message_id <= 9_223_372_036_854_775_807 else None


def _channel_url(username: str, message_id: int) -> str:
    return f"https://t.me/{username.lstrip('@')}/{message_id}"


def _book_title(
    file_name: str | None, caption_preview: str | None, media_type: str | None, message_id: int
) -> str:
    source_name = file_name or caption_preview or f"{media_type or 'file'} {message_id}"
    base_name = re.split(r"[/\\]", source_name)[-1].strip()
    base_name = strip_channel_handles(base_name)
    title = base_name.rsplit(".", 1)[0] if file_name and "." in base_name else base_name
    title = " ".join(title.split()).strip()
    return (title or f"{media_type or 'file'} {message_id}")[:MAX_BOOK_TITLE_LENGTH]


async def _search_page(
    event: Message | CallbackQuery,
    session: AsyncSession,
    query: str,
    offset: int,
) -> None:
    hits, has_next = await book_catalog.search(
        session, query, offset=offset, limit=CATALOG_PAGE_SIZE
    )
    if not hits:
        await show(event, texts.CATALOG_NO_RESULTS, keyboards.catalog_search_cancel_kb())
        return
    await show(
        event,
        texts.catalog_results(query, offset + 1, offset + len(hits)),
        keyboards.catalog_results_kb(
            [(hit.message_id, hit.file_name or "فایل بدون نام") for hit in hits],
            offset=offset,
            has_previous=offset > 0,
            has_next=has_next,
        ),
    )


@private_router.callback_query(F.data == "catalog:search")
async def on_catalog_search(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    await state.clear()
    await session.commit()
    if settings.channel_catalog_db_path is None:
        await callback.answer(texts.CATALOG_NOT_CONFIGURED, show_alert=True)
        return
    await state.set_state(SearchCatalog.waiting_for_query)
    await callback.answer()
    await show(callback, texts.CATALOG_ASK_QUERY, keyboards.catalog_search_cancel_kb())


@private_router.message(
    SearchCatalog.waiting_for_query, F.text, flags={"book_form_input": True}
)
async def on_catalog_query(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    _display, _preview, query = clean_caption(
        message.text or "", settings.channel_catalog_channel_username
    )
    if len(query) < 2:
        await message.answer(texts.CATALOG_BAD_QUERY)
        return
    await state.update_data(catalog_query=query)
    await state.set_state(None)
    try:
        await _search_page(message, session, query, 0)
    except Exception as error:
        await session.rollback()
        log.warning("book catalog search failed (%s)", type(error).__name__)
        await message.answer(texts.CATALOG_SEARCH_FAILED)


@private_router.callback_query(F.data.startswith("catalog:p:"))
async def on_catalog_page(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    match = CATALOG_PAGE_RE.fullmatch(callback.data or "")
    data = await state.get_data()
    query = data.get("catalog_query")
    if match is None or not isinstance(query, str):
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    offset = int(match[1])
    if offset > MAX_INLINE_OFFSET:
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    try:
        await _search_page(callback, session, query, offset)
    except Exception as error:
        await session.rollback()
        log.warning("book catalog page failed (%s)", type(error).__name__)
        await show(callback, texts.CATALOG_SEARCH_FAILED, keyboards.catalog_search_cancel_kb())


@private_router.callback_query(F.data == "catalog:back")
async def on_catalog_back(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    query = data.get("catalog_query")
    if not isinstance(query, str):
        await callback.answer(texts.INVALID_ACTION, show_alert=True)
        return
    await callback.answer()
    await _search_page(callback, session, query, 0)


@private_router.callback_query(F.data.startswith("catalog:open:"))
async def on_catalog_open(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    message_id = _catalog_message_id(callback.data, "open")
    entry = await book_catalog.get_entry(session, message_id) if message_id else None
    if entry is None:
        await callback.answer(texts.CATALOG_BOOK_MISSING, show_alert=True)
        return
    await callback.answer()
    await show(
        callback,
        texts.catalog_result(
            entry.file_name or "فایل بدون نام",
            entry.caption_preview,
            entry.file_size,
            entry.mime_type,
        ),
        keyboards.catalog_entry_kb(
            entry.message_id,
            _channel_url(settings.channel_catalog_channel_username, entry.message_id),
            entry.bot_file_id,
        ),
    )


@private_router.callback_query(F.data.startswith("catalog:download:"))
async def on_catalog_download(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    message_id = _catalog_message_id(callback.data, "download")
    entry = await book_catalog.get_entry(session, message_id) if message_id else None
    if entry is None:
        await callback.answer(texts.CATALOG_BOOK_MISSING, show_alert=True)
        return
    try:
        await callback.bot.copy_message(
            chat_id=callback.from_user.id,
            from_chat_id=f"@{settings.channel_catalog_channel_username.lstrip('@')}",
            message_id=entry.message_id,
        )
        await callback.answer()
    except TelegramAPIError as error:
        log.warning("catalog message copy failed (%s)", type(error).__name__)
        if entry.bot_file_id:
            try:
                await callback.bot.send_document(
                    chat_id=callback.from_user.id,
                    document=entry.bot_file_id,
                    caption=texts.catalog_result(
                        entry.file_name or "فایل بدون نام",
                        None,
                        entry.file_size,
                        entry.mime_type,
                    ),
                )
                await callback.answer()
                return
            except TelegramAPIError as fallback_error:
                log.warning(
                    "catalog document fallback failed (%s)", type(fallback_error).__name__
                )
        await callback.answer(texts.CATALOG_FILE_FAILED, show_alert=True)
        await show(
            callback,
            texts.CATALOG_FILE_FAILED,
            keyboards.catalog_entry_kb(
                entry.message_id,
                _channel_url(settings.channel_catalog_channel_username, entry.message_id),
                entry.bot_file_id,
            ),
        )
        return


@private_router.callback_query(F.data.startswith("catalog:add:"))
async def on_catalog_add(
    callback: CallbackQuery, session: AsyncSession, settings: Settings
) -> None:
    message_id = _catalog_message_id(callback.data, "add")
    entry = await book_catalog.get_entry(session, message_id) if message_id else None
    if entry is None:
        await callback.answer(texts.CATALOG_BOOK_MISSING, show_alert=True)
        return
    title = _book_title(entry.file_name, entry.caption_preview, entry.media_type, entry.message_id)
    user = await users.get_or_create(
        session,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.full_name,
    )
    result, book = await books_repo.add(
        session,
        user.id,
        title,
        None,
        None,
        catalog_message_id=entry.message_id,
    )
    if book is None:
        await session.rollback()
        await callback.answer(texts.CATALOG_BOOK_ADD_FAILED, show_alert=True)
        return
    await session.commit()
    await callback.answer(
        texts.CATALOG_BOOK_EXISTS if result == "exists" else texts.CATALOG_BOOK_ADDED
    )
    await show(
        callback,
        texts.book_detail(book.title, book.author, 0, book.total_pages, book.status),
        keyboards.book_detail_with_pages_kb(
            book.id,
            book.status,
            has_page_count=book.total_pages is not None,
            catalog_message_id=book.catalog_message_id,
            catalog_url=(
                _channel_url(
                    settings.channel_catalog_channel_username, book.catalog_message_id
                )
                if book.catalog_message_id is not None
                else None
            ),
        ),
    )


@router.inline_query()
async def on_catalog_inline_query(
    query: InlineQuery, session: AsyncSession, settings: Settings
) -> None:
    if settings.channel_catalog_db_path is None:
        await query.answer([], cache_time=5, is_personal=True)
        return
    _display, _preview, search_query = clean_caption(
        query.query, settings.channel_catalog_channel_username
    )
    try:
        offset = min(max(int(query.offset or "0"), 0), MAX_INLINE_OFFSET)
    except ValueError:
        offset = 0
    results = []
    next_offset = ""
    if len(search_query) >= 2:
        try:
            hits, has_next = await book_catalog.search(
                session, search_query, offset=offset, limit=CATALOG_PAGE_SIZE
            )
            for hit in hits:
                file_name = strip_channel_handles(hit.file_name or "فایل بدون نام")
                post_url = _channel_url(settings.channel_catalog_channel_username, hit.message_id)
                caption = texts.catalog_result(
                    file_name, hit.caption_preview, hit.file_size, hit.mime_type
                )
                if hit.bot_file_id:
                    results.append(
                        InlineQueryResultCachedDocument(
                            id=str(hit.message_id),
                            title=file_name[:64],
                            document_file_id=hit.bot_file_id,
                            description=strip_channel_handles(hit.caption_preview or "")[:128],
                            caption=caption,
                        )
                    )
                else:
                    results.append(
                        InlineQueryResultArticle(
                            id=str(hit.message_id),
                            title=file_name[:64],
                            description=strip_channel_handles(
                                hit.caption_preview or "لینک پست کانال"
                            )[:128],
                            input_message_content=InputTextMessageContent(
                                message_text=f"{caption}\n<a href=\"{post_url}\">مشاهدهٔ پست</a>"
                            ),
                        )
                    )
            if has_next:
                next_offset = str(offset + len(hits))
        except Exception as error:
            log.warning("book catalog inline search failed (%s)", type(error).__name__)
    await query.answer(
        results,
        cache_time=5,
        is_personal=True,
        next_offset=next_offset,
    )