import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA.repositories import book_catalog
from BOOKzMA.services.catalog_text import (
    SEARCH_TEXT_LIMIT,
    build_search_document,
    clean_caption,
    normalize_catalog_text,
    search_document_hash,
)
from BOOKzMA.services.meilisearch import MeilisearchClient

log = logging.getLogger(__name__)
BATCH_SIZE = 1000
REINDEX_BATCH_SIZE = 10_000
OUTBOX_BATCH_SIZE = 1000


@dataclass(frozen=True)
class SourceBatch:
    entries: list[dict[str, object]]
    next_source_row_id: int
    source_rows: int


def seconds_until_next_sync(now: datetime, sync_hour_utc: int) -> float:
    current = now.astimezone(timezone.utc)
    next_run = datetime.combine(
        current.date(), time(hour=sync_hour_utc), tzinfo=timezone.utc
    )
    if next_run <= current:
        next_run += timedelta(days=1)
    return (next_run - current).total_seconds()


def _read_source_batch(
    database_path: Path,
    channel_username: str,
    after_row_id: int,
    batch_size: int,
) -> SourceBatch:
    uri = f"{database_path.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=0.25, isolation_level=None)
    connection.execute("PRAGMA query_only = ON")
    try:
        main_channel = connection.execute(
            "SELECT id, username FROM channels WHERE is_main = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        configured_username = channel_username.lstrip("@").casefold()
        if main_channel is None or main_channel[1].casefold() != configured_username:
            raise ValueError("configured catalog channel is not the SQLite main channel")

        rows = connection.execute(
            """
            SELECT id, message_id, file_name, file_size, mime_type, media_type, date,
                   text, in_main, is_duplicate
            FROM messages
            WHERE channel_id = ? AND id > ?
            ORDER BY id
            LIMIT ?
            """,
            (main_channel[0], after_row_id, batch_size),
        ).fetchall()
    finally:
        connection.close()

    entries: list[dict[str, object]] = []
    for row in rows:
        (
            source_row_id,
            message_id,
            file_name,
            file_size,
            mime_type,
            media_type,
            posted_at,
            caption,
            in_main,
            is_duplicate,
        ) = row
        if not in_main or is_duplicate or not message_id or message_id <= 0:
            continue
        _caption_display, caption_preview, caption_search = clean_caption(
            caption, channel_username
        )
        search_text = normalize_catalog_text(
            f"{file_name or ''} {caption_search}"
        )[:SEARCH_TEXT_LIMIT]
        entries.append(
            {
                "message_id": int(message_id),
                "source_row_id": int(source_row_id),
                "file_name": str(file_name)[:1000] if file_name else None,
                "caption_preview": caption_preview or None,
                "caption_search": caption_search,
                "search_text": search_text,
                "media_type": str(media_type)[:32] if media_type else None,
                "mime_type": str(mime_type)[:255] if mime_type else None,
                "file_size": int(file_size) if file_size is not None else None,
                "posted_at": str(posted_at)[:64] if posted_at else None,
            }
        )

    return SourceBatch(
        entries=entries,
        next_source_row_id=int(rows[-1][0]) if rows else after_row_id,
        source_rows=len(rows),
    )


def _search_document(entry: dict[str, object]) -> dict[str, Any]:
    return build_search_document(
        message_id=int(entry["message_id"]),
        file_name=str(entry["file_name"]) if entry.get("file_name") else None,
        caption_preview=(
            str(entry["caption_preview"]) if entry.get("caption_preview") else None
        ),
        caption_search=str(entry.get("caption_search") or ""),
        file_size=int(entry["file_size"]) if entry.get("file_size") is not None else None,
        mime_type=str(entry["mime_type"]) if entry.get("mime_type") else None,
        media_type=str(entry["media_type"]) if entry.get("media_type") else None,
        posted_at=str(entry["posted_at"]) if entry.get("posted_at") else None,
    )


async def flush_pending_index_operations(
    session_pool: async_sessionmaker[AsyncSession],
    meilisearch: MeilisearchClient,
    *,
    batch_size: int = OUTBOX_BATCH_SIZE,
) -> int:
    completed = 0
    while True:
        async with session_pool() as session:
            operations = await book_catalog.pending_index_operations(
                session, limit=batch_size
            )
        if not operations:
            return completed

        documents = [
            operation.document
            for operation in operations
            if operation.operation == "upsert" and operation.document is not None
        ]
        message_ids = [
            operation.message_id
            for operation in operations
            if operation.operation == "delete"
        ]
        try:
            if documents:
                await meilisearch.add_documents(documents, wait=True)
            if message_ids:
                await meilisearch.delete_documents(message_ids, wait=True)
        except Exception as error:
            async with session_pool.begin() as session:
                await book_catalog.record_index_operation_failure(
                    session, operations, type(error).__name__
                )
            raise

        async with session_pool.begin() as session:
            await book_catalog.acknowledge_index_operations(session, operations)
        completed += len(operations)


async def _flush_index_outbox(
    session_pool: async_sessionmaker[AsyncSession],
    meilisearch: MeilisearchClient,
    *,
    fail_on_error: bool,
) -> bool:
    try:
        await flush_pending_index_operations(session_pool, meilisearch)
    except Exception as error:
        async with session_pool.begin() as session:
            await book_catalog.mark_sync_error(session, type(error).__name__)
        if fail_on_error:
            raise
        return False
    return True


async def sync_once(
    session_pool: async_sessionmaker[AsyncSession],
    database_path: Path,
    channel_username: str,
    *,
    meilisearch: MeilisearchClient | None = None,
    batch_size: int = BATCH_SIZE,
    force_reindex: bool = False,
) -> int:
    meilisearch_available = meilisearch is not None
    if meilisearch is not None:
        meilisearch_available = await _flush_index_outbox(
            session_pool, meilisearch, fail_on_error=force_reindex
        )

    changed_count = 0
    cursor = 0
    while True:
        batch = await asyncio.to_thread(
            _read_source_batch,
            database_path,
            channel_username,
            cursor,
            batch_size,
        )
        if not batch.source_rows:
            async with session_pool.begin() as session:
                stale_entries = await book_catalog.source_entries_in_range(
                    session, cursor, 9_223_372_036_854_775_807
                )
                stale_ids = [entry.message_id for entry in stale_entries]
                await book_catalog.delete_entries(session, stale_ids)
                await book_catalog.queue_index_deletes(session, stale_ids)
                await book_catalog.set_sync_cursor(session, cursor)
            if meilisearch is not None:
                if meilisearch_available:
                    meilisearch_available = await _flush_index_outbox(
                        session_pool, meilisearch, fail_on_error=force_reindex
                    )
            async with session_pool.begin() as session:
                await book_catalog.mark_sync_success(
                    session,
                    datetime.now(timezone.utc),
                    clear_error=meilisearch_available,
                )
            return changed_count

        index_documents = []
        async with session_pool.begin() as session:
            existing_entries = await book_catalog.source_entries_in_range(
                session, cursor, batch.next_source_row_id
            )
            existing_by_source_id = {
                entry.source_row_id: entry for entry in existing_entries
            }
            incoming_by_source_id = {
                int(entry["source_row_id"]): entry for entry in batch.entries
            }
            stale_ids = [
                existing.message_id
                for source_row_id, existing in existing_by_source_id.items()
                if source_row_id not in incoming_by_source_id
                or int(incoming_by_source_id[source_row_id]["message_id"])
                != existing.message_id
            ]
            await book_catalog.delete_entries(session, stale_ids)
            await book_catalog.queue_index_deletes(session, stale_ids)

            changed_entries = []
            for source_row_id, entry in incoming_by_source_id.items():
                document = _search_document(entry)
                document_hash = search_document_hash(document)
                entry["document_hash"] = document_hash
                existing = existing_by_source_id.get(source_row_id)
                if (
                    force_reindex
                    or existing is None
                    or existing.message_id != int(entry["message_id"])
                    or existing.document_hash != document_hash
                ):
                    changed_entries.append(entry)
                    index_documents.append(document)

            await book_catalog.upsert_batch(
                session, changed_entries, next_source_row_id=batch.next_source_row_id
            )
            await book_catalog.queue_index_upserts(session, index_documents)

        changed_count += len(index_documents) + len(stale_ids)
        if meilisearch is not None and meilisearch_available:
            meilisearch_available = await _flush_index_outbox(
                session_pool, meilisearch, fail_on_error=force_reindex
            )
        cursor = batch.next_source_row_id


async def _record_sync_error(
    session_pool: async_sessionmaker[AsyncSession], error: Exception
) -> None:
    async with session_pool.begin() as session:
        await book_catalog.mark_sync_error(session, type(error).__name__)


async def book_catalog_sync_loop(
    session_pool: async_sessionmaker[AsyncSession],
    database_path: Path,
    channel_username: str,
    sync_hour_utc: int,
    meilisearch: MeilisearchClient | None = None,
) -> None:
    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep(seconds_until_next_sync(now, sync_hour_utc))

        try:
            changed = await sync_once(
                session_pool,
                database_path,
                channel_username,
                meilisearch=meilisearch,
            )
            log.info("book catalog sync completed; rows changed=%s", changed)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            try:
                await _record_sync_error(session_pool, error)
            except Exception:
                log.error("book catalog sync error state could not be saved")
            log.error("book catalog sync failed (%s)", type(error).__name__)
