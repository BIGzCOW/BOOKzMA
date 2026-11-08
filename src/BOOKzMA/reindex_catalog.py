import asyncio
import logging

from BOOKzMA.config import CatalogSettings
from BOOKzMA.db.session import create_session_pool
from BOOKzMA.repositories import book_catalog
from BOOKzMA.services.book_catalog_sync import REINDEX_BATCH_SIZE, sync_once
from BOOKzMA.services.meilisearch import MeilisearchClient

log = logging.getLogger(__name__)


async def reindex_catalog(settings: CatalogSettings) -> tuple[int, int]:
    database_path = settings.channel_catalog_db_path
    if database_path is None or not database_path.is_file():
        raise RuntimeError("The configured read-only SQLite catalog file is unavailable")
    if settings.meili_url is None or settings.meili_api_key is None:
        raise RuntimeError("MEILI_URL and MEILI_API_KEY are required for catalog reindex")

    engine, session_pool = create_session_pool(settings.database_url)
    meilisearch = MeilisearchClient(
        str(settings.meili_url),
        settings.meili_api_key.get_secret_value(),
        settings.meili_index_name,
        timeout=settings.meili_timeout_seconds,
    )
    try:
        await meilisearch.ensure_index()
        changed = await sync_once(
            session_pool,
            database_path,
            settings.channel_catalog_channel_username,
            meilisearch=meilisearch,
            batch_size=REINDEX_BATCH_SIZE,
            force_reindex=True,
        )
        async with session_pool() as session:
            expected_count = await book_catalog.entry_count(session)
            pending_count = await book_catalog.pending_operation_count(session)
        stats = await meilisearch.index_stats()
        indexed_count = stats.get("numberOfDocuments")
        if pending_count:
            raise RuntimeError(f"catalog reindex left {pending_count} pending index operations")
        if indexed_count != expected_count:
            raise RuntimeError(
                f"catalog index count mismatch: PostgreSQL={expected_count}, "
                f"Meilisearch={indexed_count}"
            )
        log.info(
            "catalog reindex complete; changed=%s documents=%s",
            changed,
            indexed_count,
        )
        return changed, expected_count
    finally:
        await meilisearch.aclose()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(reindex_catalog(CatalogSettings()))
    except Exception as error:
        log.error("catalog reindex failed (%s)", type(error).__name__)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()