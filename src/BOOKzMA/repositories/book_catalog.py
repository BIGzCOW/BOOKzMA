from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import BookCatalogEntry, BookCatalogSyncState
from BOOKzMA.services.catalog_text import normalize_catalog_text


@dataclass(frozen=True)
class CatalogHit:
    message_id: int
    file_name: str | None
    caption_preview: str | None
    media_type: str | None
    mime_type: str | None
    file_size: int | None
    bot_file_id: str | None


async def search(
    session: AsyncSession,
    query: str,
    *,
    offset: int,
    limit: int,
) -> tuple[list[CatalogHit], bool]:
    normalized_query = normalize_catalog_text(query)[:120]
    if not normalized_query or offset < 0 or limit < 1:
        return [], False

    ts_query = func.websearch_to_tsquery("simple", normalized_query)
    rank = func.ts_rank_cd(BookCatalogEntry.search_vector, ts_query)
    result = await session.execute(
        select(
            BookCatalogEntry.message_id,
            BookCatalogEntry.file_name,
            BookCatalogEntry.caption_preview,
            BookCatalogEntry.media_type,
            BookCatalogEntry.mime_type,
            BookCatalogEntry.file_size,
            BookCatalogEntry.bot_file_id,
        )
        .where(BookCatalogEntry.search_vector.op("@@")(ts_query))
        .order_by(rank.desc(), BookCatalogEntry.message_id.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = result.all()
    has_next = len(rows) > limit
    return [CatalogHit(*row) for row in rows[:limit]], has_next


async def get_entry(session: AsyncSession, message_id: int) -> BookCatalogEntry | None:
    return await session.get(BookCatalogEntry, message_id)


async def sync_cursor(session: AsyncSession) -> int:
    state = await session.get(BookCatalogSyncState, "main")
    return state.source_row_id if state is not None else 0


async def upsert_batch(
    session: AsyncSession,
    entries: list[dict[str, object]],
    *,
    next_source_row_id: int,
) -> None:
    if entries:
        statement = insert(BookCatalogEntry).values(entries)
        excluded = statement.excluded
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[BookCatalogEntry.message_id],
                set_={
                    "source_row_id": excluded.source_row_id,
                    "file_name": excluded.file_name,
                    "caption_preview": excluded.caption_preview,
                    "caption_search": excluded.caption_search,
                    "search_text": excluded.search_text,
                    "media_type": excluded.media_type,
                    "mime_type": excluded.mime_type,
                    "file_size": excluded.file_size,
                    "posted_at": excluded.posted_at,
                    "bot_file_id": func.coalesce(
                        excluded.bot_file_id, BookCatalogEntry.bot_file_id
                    ),
                },
            )
        )

    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.source_row_id = max(state.source_row_id, next_source_row_id)
    state.last_error = None


async def mark_sync_success(session: AsyncSession, completed_at: datetime) -> None:
    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.last_success_at = completed_at
    state.last_error = None


async def mark_sync_error(session: AsyncSession, error_name: str) -> None:
    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.last_error = error_name[:255]
