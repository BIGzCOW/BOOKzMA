from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from BOOKzMA.db.models import (
    BookCatalogEntry,
    BookCatalogIndexOutbox,
    BookCatalogSyncState,
)
from BOOKzMA.services.catalog_text import normalize_catalog_text
from BOOKzMA.services.meilisearch import MAX_TOTAL_HITS, MeilisearchClient, MeilisearchUnavailable


@dataclass(frozen=True)
class CatalogHit:
    message_id: int
    file_name: str | None
    caption_preview: str | None
    media_type: str | None
    mime_type: str | None
    file_size: int | None


@dataclass(frozen=True)
class CatalogIndexOperation:
    id: int
    message_id: int
    operation: str
    document: dict[str, object] | None
    revision: int


async def search(
    session: AsyncSession,
    query: str,
    *,
    offset: int,
    limit: int,
    meilisearch: MeilisearchClient | None = None,
) -> tuple[list[CatalogHit], bool]:
    normalized_query = normalize_catalog_text(query)[:120]
    if not normalized_query or len(normalized_query) < 2 or offset < 0 or limit < 1:
        return [], False
    if meilisearch is None:
        raise MeilisearchUnavailable("Meilisearch is not configured")
    if offset >= MAX_TOTAL_HITS:
        return [], False
    hits, has_next = await meilisearch.search(
        normalized_query,
        offset=offset,
        limit=min(limit, MAX_TOTAL_HITS - offset),
    )
    return [
        CatalogHit(
            message_id=int(hit["id"]),
            file_name=(hit.get("display_file_name") or hit.get("file_name")),
            caption_preview=hit.get("caption_preview"),
            media_type=hit.get("media_type"),
            mime_type=hit.get("mime_type"),
            file_size=hit.get("file_size"),
        )
        for hit in hits
        if isinstance(hit, dict) and isinstance(hit.get("id"), int)
    ], has_next


async def get_entry(session: AsyncSession, message_id: int) -> BookCatalogEntry | None:
    return await session.get(BookCatalogEntry, message_id)


async def sync_cursor(session: AsyncSession) -> int:
    state = await session.get(BookCatalogSyncState, "main")
    if state is None:
        return 0
    return state.source_row_id or 0


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
                    "document_hash": excluded.document_hash,
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
    state.source_row_id = next_source_row_id


async def set_sync_cursor(session: AsyncSession, source_row_id: int) -> None:
    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.source_row_id = source_row_id


async def source_entries_in_range(
    session: AsyncSession, after_source_row_id: int, through_source_row_id: int
) -> list[BookCatalogEntry]:
    if through_source_row_id <= after_source_row_id:
        return []
    result = await session.scalars(
        select(BookCatalogEntry)
        .where(
            BookCatalogEntry.source_row_id > after_source_row_id,
            BookCatalogEntry.source_row_id <= through_source_row_id,
        )
        .order_by(BookCatalogEntry.source_row_id)
    )
    return list(result.all())


async def delete_entries(session: AsyncSession, message_ids: list[int]) -> None:
    if message_ids:
        await session.execute(
            delete(BookCatalogEntry).where(BookCatalogEntry.message_id.in_(message_ids))
        )


async def queue_index_upserts(
    session: AsyncSession, documents: list[dict[str, object]]
) -> None:
    if not documents:
        return
    statement = insert(BookCatalogIndexOutbox).values(
        [
            {
                "message_id": int(document["id"]),
                "operation": "upsert",
                "document": document,
            }
            for document in documents
        ]
    )
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[BookCatalogIndexOutbox.message_id],
            set_={
                "operation": excluded.operation,
                "document": excluded.document,
                "revision": BookCatalogIndexOutbox.revision + 1,
                "attempts": 0,
                "last_error": None,
                "created_at": func.now(),
            },
        )
    )


async def queue_index_deletes(session: AsyncSession, message_ids: list[int]) -> None:
    if not message_ids:
        return
    statement = insert(BookCatalogIndexOutbox).values(
        [
            {"message_id": message_id, "operation": "delete", "document": None}
            for message_id in message_ids
        ]
    )
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[BookCatalogIndexOutbox.message_id],
            set_={
                "operation": excluded.operation,
                "document": None,
                "revision": BookCatalogIndexOutbox.revision + 1,
                "attempts": 0,
                "last_error": None,
                "created_at": func.now(),
            },
        )
    )


async def pending_index_operations(
    session: AsyncSession, *, limit: int
) -> list[CatalogIndexOperation]:
    result = await session.scalars(
        select(BookCatalogIndexOutbox)
        .order_by(BookCatalogIndexOutbox.created_at, BookCatalogIndexOutbox.id)
        .limit(limit)
    )
    return [
        CatalogIndexOperation(
            row.id, row.message_id, row.operation, row.document, row.revision
        )
        for row in result.all()
    ]


async def acknowledge_index_operations(
    session: AsyncSession, operations: list[CatalogIndexOperation]
) -> None:
    if not operations:
        return
    await session.execute(
        delete(BookCatalogIndexOutbox).where(
            tuple_(BookCatalogIndexOutbox.id, BookCatalogIndexOutbox.revision).in_(
                [(operation.id, operation.revision) for operation in operations]
            )
        )
    )


async def record_index_operation_failure(
    session: AsyncSession,
    operations: list[CatalogIndexOperation],
    error_name: str,
) -> None:
    if not operations:
        return
    await session.execute(
        update(BookCatalogIndexOutbox)
        .where(
            tuple_(BookCatalogIndexOutbox.id, BookCatalogIndexOutbox.revision).in_(
                [(operation.id, operation.revision) for operation in operations]
            )
        )
        .values(
            attempts=BookCatalogIndexOutbox.attempts + 1,
            last_error=error_name[:64],
        )
    )


async def entry_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(BookCatalogEntry)
            .where(BookCatalogEntry.source_row_id > 0)
        )
        or 0
    )


async def pending_operation_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(BookCatalogIndexOutbox)) or 0
    )


async def mark_sync_success(
    session: AsyncSession, completed_at: datetime, *, clear_error: bool = True
) -> None:
    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.last_success_at = completed_at
    if clear_error:
        state.last_error = None


async def mark_sync_error(session: AsyncSession, error_name: str) -> None:
    state = await session.get(BookCatalogSyncState, "main", with_for_update=True)
    if state is None:
        state = BookCatalogSyncState(key="main")
        session.add(state)
    state.last_error = error_name[:255]
