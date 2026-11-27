import asyncio
import os
import random
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from BOOKzMA.db.models import (
    BookCatalogEntry,
    BookCatalogIndexOutbox,
    BookCatalogSyncState,
)
from BOOKzMA.repositories import book_catalog
from BOOKzMA.services.book_catalog_sync import sync_once
from BOOKzMA.services.catalog_text import search_document_hash, build_search_document

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL must point to a disposable PostgreSQL database",
)


def test_catalog_upsert_search_and_sync_cursor_are_idempotent():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        message_id = 7_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        source_row_id = 6_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            async with pool.begin() as session:
                await book_catalog.upsert_batch(
                    session,
                    [
                        {
                            "message_id": message_id,
                            "source_row_id": source_row_id,
                            "file_name": "مرگ_فروشنده.pdf",
                            "caption_preview": "نمایشنامهٔ آرتور میلر",
                            "caption_search": "نمایشنامهٔ آرتور میلر",
                            "search_text": "مرگ فروشنده pdf نمایشنامه ارتور میلر",
                            "media_type": "Document",
                            "mime_type": "application/pdf",
                            "file_size": 1234,
                            "posted_at": "2026-11-03T10:00:00+00:00",
                        }
                    ],
                    next_source_row_id=source_row_id,
                )
            async with pool.begin() as session:
                await book_catalog.upsert_batch(
                    session,
                    [
                        {
                            "message_id": message_id,
                            "source_row_id": source_row_id,
                            "file_name": "مرگ_فروشنده.pdf",
                            "caption_preview": "نمایشنامهٔ آرتور میلر",
                            "caption_search": "نمایشنامهٔ آرتور میلر",
                            "search_text": "مرگ فروشنده pdf نمایشنامه ارتور میلر",
                            "media_type": "Document",
                            "mime_type": "application/pdf",
                            "file_size": 1234,
                            "posted_at": "2026-11-03T10:00:00+00:00",
                        }
                    ],
                    next_source_row_id=source_row_id,
                )
                assert await book_catalog.sync_cursor(session) == source_row_id
                entries = await session.scalars(
                    select(BookCatalogEntry).where(BookCatalogEntry.message_id == message_id)
                )
                assert len(list(entries)) == 1
        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogEntry).where(BookCatalogEntry.message_id == message_id)
                )
                await session.execute(
                    update(BookCatalogSyncState)
                    .where(BookCatalogSyncState.key == "main")
                    .values(source_row_id=0, last_success_at=None, last_error=None)
                )
            await engine.dispose()

    asyncio.run(run_test())


def test_catalog_sync_imports_only_main_channel_and_skips_raw_data(tmp_path: Path):
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        source_database = tmp_path / "channel_data.db"
        connection = sqlite3.connect(source_database)
        connection.executescript(
            """
            CREATE TABLE channels (id INTEGER, username TEXT, is_main INTEGER);
            CREATE TABLE messages (
                id INTEGER, message_id INTEGER, channel_id INTEGER, file_name TEXT,
                file_size INTEGER, mime_type TEXT, media_type TEXT, date TEXT,
                text TEXT, in_main INTEGER, is_duplicate INTEGER, raw_data TEXT
            );
            INSERT INTO channels VALUES (24, 'BOOKzMA', 1);
            INSERT INTO channels VALUES (25, 'other', 0);
            INSERT INTO messages VALUES
                (5, 201, 24, 'Ketab.pdf', 1000, 'application/pdf', 'Document',
                 '2026-11-03', 'یک عنوان @BOOKzMA', 1, 0, 'PRIVATE_RAW');
            INSERT INTO messages VALUES
                (6, 202, 25, 'Other.pdf', 1000, 'application/pdf', 'Document',
                 '2026-11-03', 'کانال دیگر', 0, 0, 'PRIVATE_RAW');
            INSERT INTO messages VALUES
                (7, 203, 24, 'Duplicate.pdf', 1000, 'application/pdf', 'Document',
                 '2026-11-03', 'تکراری', 1, 1, 'PRIVATE_RAW');
            """
        )
        connection.close()
        try:
            imported = await sync_once(pool, source_database, "BOOKzMA")
            assert imported == 1
            async with pool() as session:
                entry = await session.get(BookCatalogEntry, 201)
                assert entry is not None
                assert entry.caption_preview == "یک عنوان"
                assert entry.search_text == "ketab.pdf یک عنوان"
                assert await session.get(BookCatalogEntry, 202) is None
                assert await session.get(BookCatalogEntry, 203) is None
                assert await book_catalog.sync_cursor(session) == 7
        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogIndexOutbox).where(
                        BookCatalogIndexOutbox.message_id.in_([201, 202, 203])
                    )
                )
                await session.execute(
                    delete(BookCatalogEntry).where(BookCatalogEntry.message_id.in_([201, 202, 203]))
                )
                await session.execute(
                    update(BookCatalogSyncState)
                    .where(BookCatalogSyncState.key == "main")
                    .values(source_row_id=0, last_success_at=None, last_error=None)
                )
            await engine.dispose()

    asyncio.run(run_test())


def test_catalog_sync_reconciles_source_updates_deletes_and_new_documents(tmp_path: Path):
    class FakeMeilisearch:
        def __init__(self) -> None:
            self.documents = {}
            self.fail_next_add = False

        async def add_documents(self, documents, *, wait=True):
            if self.fail_next_add:
                self.fail_next_add = False
                raise RuntimeError("temporary indexing failure")
            for document in documents:
                self.documents[document["id"]] = dict(document)

        async def delete_documents(self, message_ids, *, wait=True):
            for message_id in message_ids:
                self.documents.pop(message_id, None)

    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        source_database = tmp_path / "channel_data.db"
        connection = sqlite3.connect(source_database)
        connection.executescript(
            """
            CREATE TABLE channels (id INTEGER, username TEXT, is_main INTEGER);
            CREATE TABLE messages (
                id INTEGER, message_id INTEGER, channel_id INTEGER, file_name TEXT,
                file_size INTEGER, mime_type TEXT, media_type TEXT, date TEXT,
                text TEXT, in_main INTEGER, is_duplicate INTEGER, raw_data TEXT
            );
            INSERT INTO channels VALUES (24, 'BOOKzMA', 1);
            """
        )
        source_row_id = 8_000_000_000_000_000_000 + random.randrange(1_000_000)
        message_id = 7_000_000_000_000_000_000 + random.randrange(1_000_000)

        def insert_source(row_id: int, post_id: int, name: str, caption: str) -> None:
            connection.execute(
                "INSERT INTO messages VALUES (?, ?, 24, ?, 1000, 'application/pdf', "
                "'Document', '2026-11-03', ?, 1, 0, 'PRIVATE_RAW')",
                (row_id, post_id, name, caption),
            )

        insert_source(source_row_id, message_id, "First.pdf", "Original caption")
        insert_source(source_row_id + 1, message_id + 1, "Removed.pdf", "To be removed")
        connection.commit()
        connection.close()
        search_index = FakeMeilisearch()
        search_index.fail_next_add = True
        try:
            first_changed = await sync_once(
                pool, source_database, "BOOKzMA", meilisearch=search_index, batch_size=1
            )
            assert first_changed == 2
            assert search_index.documents == {}
            async with pool() as session:
                assert await book_catalog.pending_operation_count(session) == 2
                state = await session.get(BookCatalogSyncState, "main")
                assert state.last_error == "RuntimeError"

            second_changed = await sync_once(
                pool, source_database, "BOOKzMA", meilisearch=search_index, batch_size=1
            )
            assert second_changed == 0
            assert set(search_index.documents) == {message_id, message_id + 1}
            async with pool() as session:
                assert await book_catalog.pending_operation_count(session) == 0
                state = await session.get(BookCatalogSyncState, "main")
                assert state.last_error is None

            connection = sqlite3.connect(source_database)
            connection.execute(
                "UPDATE messages SET text = 'Updated caption' WHERE id = ?",
                (source_row_id,),
            )
            connection.execute("DELETE FROM messages WHERE id = ?", (source_row_id + 1,))
            insert_source(source_row_id + 2, message_id + 2, "Added.pdf", "New caption")
            connection.commit()
            connection.close()

            changed = await sync_once(
                pool, source_database, "BOOKzMA", meilisearch=search_index, batch_size=1
            )
            assert changed == 3
            assert set(search_index.documents) == {message_id, message_id + 2}
            assert search_index.documents[message_id]["caption"] == "updated caption"
            assert search_index.documents[message_id + 2]["title"] == "added"
            async with pool() as session:
                assert await session.get(BookCatalogEntry, message_id + 1) is None
                assert await book_catalog.pending_operation_count(session) == 0
        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogIndexOutbox).where(
                        BookCatalogIndexOutbox.message_id.in_(
                            [message_id, message_id + 1, message_id + 2]
                        )
                    )
                )
                await session.execute(
                    delete(BookCatalogEntry).where(
                        BookCatalogEntry.message_id.in_(
                            [message_id, message_id + 1, message_id + 2]
                        )
                    )
                )
                await session.execute(
                    update(BookCatalogSyncState)
                    .where(BookCatalogSyncState.key == "main")
                    .values(source_row_id=0, last_success_at=None, last_error=None)
                )
            await engine.dispose()

    asyncio.run(run_test())


def test_catalog_outbox_queues_upserts_and_deletes_with_hash_dedup():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        message_id = 7_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            doc1 = build_search_document(
                message_id=message_id,
                file_name="Book.pdf",
                caption_preview="Caption 1",
                caption_search="Caption 1",
                file_size=1000,
                mime_type="application/pdf",
                media_type="Document",
                posted_at="2026-11-07T10:00:00+00:00",
            )
            doc2 = build_search_document(
                message_id=message_id + 1,
                file_name="Book2.pdf",
                caption_preview="Caption 2",
                caption_search="Caption 2",
                file_size=2000,
                mime_type="application/pdf",
                media_type="Document",
                posted_at="2026-11-07T11:00:00+00:00",
            )
            hash1 = search_document_hash(doc1)
            hash2 = search_document_hash(doc2)
            assert hash1 != hash2

            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [doc1, doc2])
                await book_catalog.queue_index_deletes(session, [message_id + 2])

            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 3
                upserts = [op for op in pending if op.operation == "upsert"]
                deletes = [op for op in pending if op.operation == "delete"]
                assert len(upserts) == 2
                assert len(deletes) == 1
                assert upserts[0].document is not None
                assert upserts[0].document["id"] == message_id
                assert deletes[0].message_id == message_id + 2
                assert deletes[0].document is None

            # Re-queue same documents (should update revision, not duplicate)
            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [doc1])
            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 3
                # The upsert for message_id should have revision 2 now
                ops = [
                    op for op in pending if op.message_id == message_id and op.operation == "upsert"
                ]
                op = next(iter(ops))
                assert op.revision == 2

        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogIndexOutbox).where(
                        BookCatalogIndexOutbox.message_id.in_(
                            [message_id, message_id + 1, message_id + 2]
                        )
                    )
                )
            await engine.dispose()

    asyncio.run(run_test())


def test_catalog_outbox_acknowledge_and_record_failure():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        message_id = 7_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            doc = build_search_document(
                message_id=message_id,
                file_name="Book.pdf",
                caption_preview="Caption",
                caption_search="Caption",
                file_size=1000,
                mime_type="application/pdf",
                media_type="Document",
                posted_at="2026-11-07T10:00:00+00:00",
            )
            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [doc])
                await book_catalog.queue_index_deletes(session, [message_id + 1])

            async with pool.begin() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 2
                await book_catalog.acknowledge_index_operations(session, pending)

            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 0

            # Test record failure
            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [doc])
            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 1
                await book_catalog.record_index_operation_failure(session, pending, "TestError")
                await session.commit()

            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 1
                assert pending[0].attempts == 1
                assert pending[0].last_error == "TestError"

        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogIndexOutbox).where(
                        BookCatalogIndexOutbox.message_id.in_([message_id, message_id + 1])
                    )
                )
            await engine.dispose()

    asyncio.run(run_test())


def test_catalog_outbox_hash_dedup_prevents_duplicate_upserts():
    async def run_test() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        pool = async_sessionmaker(engine, expire_on_commit=False)
        message_id = 7_000_000_000_000_000_000 + random.randrange(1_000_000_000)
        try:
            doc = build_search_document(
                message_id=message_id,
                file_name="Book.pdf",
                caption_preview="Caption",
                caption_search="Caption",
                file_size=1000,
                mime_type="application/pdf",
                media_type="Document",
                posted_at="2026-11-07T10:00:00+00:00",
            )
            doc_hash = search_document_hash(doc)

            async with pool.begin() as session:
                # First upsert
                await book_catalog.queue_index_upserts(session, [doc])
            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 1
                assert pending[0].document is not None
                assert search_document_hash(pending[0].document) == doc_hash
                first_revision = pending[0].revision

            # Second upsert with identical document (simulating reindex with no changes)
            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [doc])
            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 1
                # Revision should increment but document hash same
                assert pending[0].revision == first_revision + 1
                assert search_document_hash(pending[0].document) == doc_hash

            # Third upsert with modified document
            modified_doc = build_search_document(
                message_id=message_id,
                file_name="Book.pdf",
                caption_preview="Modified Caption",
                caption_search="Modified Caption",
                file_size=1000,
                mime_type="application/pdf",
                media_type="Document",
                posted_at="2026-11-07T10:00:00+00:00",
            )
            async with pool.begin() as session:
                await book_catalog.queue_index_upserts(session, [modified_doc])
            async with pool() as session:
                pending = await book_catalog.pending_index_operations(session, limit=10)
                assert len(pending) == 1
                assert search_document_hash(pending[0].document) != doc_hash

        finally:
            async with pool.begin() as session:
                await session.execute(
                    delete(BookCatalogIndexOutbox).where(
                        BookCatalogIndexOutbox.message_id == message_id
                    )
                )
            await engine.dispose()

    asyncio.run(run_test())
