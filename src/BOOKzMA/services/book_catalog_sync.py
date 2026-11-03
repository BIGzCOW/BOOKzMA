import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA.repositories import book_catalog
from BOOKzMA.services.catalog_text import (
    SEARCH_TEXT_LIMIT,
    clean_caption,
    normalize_catalog_text,
)

log = logging.getLogger(__name__)
BATCH_SIZE = 1000
@dataclass(frozen=True)
class SourceBatch:
    entries: list[dict[str, object]]
    next_source_row_id: int
    source_rows: int


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


async def sync_once(
    session_pool: async_sessionmaker[AsyncSession],
    database_path: Path,
    channel_username: str,
) -> int:
    async with session_pool() as session:
        cursor = await book_catalog.sync_cursor(session)

    imported = 0
    while True:
        batch = await asyncio.to_thread(
            _read_source_batch,
            database_path,
            channel_username,
            cursor,
            BATCH_SIZE,
        )
        if not batch.source_rows:
            async with session_pool.begin() as session:
                await book_catalog.mark_sync_success(session, datetime.now(timezone.utc))
            return imported

        async with session_pool.begin() as session:
            await book_catalog.upsert_batch(
                session,
                batch.entries,
                next_source_row_id=batch.next_source_row_id,
            )
        imported += len(batch.entries)
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
) -> None:
    while True:
        try:
            imported = await sync_once(session_pool, database_path, channel_username)
            log.info("book catalog sync completed; rows upserted=%s", imported)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            try:
                await _record_sync_error(session_pool, error)
            except Exception:
                log.error("book catalog sync error state could not be saved")
            log.error("book catalog sync failed (%s)", type(error).__name__)

        now = datetime.now(timezone.utc)
        next_run = datetime.combine(
            now.date(), time(hour=sync_hour_utc), tzinfo=timezone.utc
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())