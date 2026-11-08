import asyncio

import httpx
import pytest

from BOOKzMA.services.meilisearch import (
    MEILISEARCH_INDEX_SETTINGS,
    MeilisearchClient,
    MeilisearchUnavailable,
)
from BOOKzMA.config import CatalogSettings
from BOOKzMA.repositories import book_catalog


def test_search_sends_normalized_pagination_and_returns_has_next():
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "hits": [{"id": 11}, {"id": 12}],
                "estimatedTotalHits": 4,
            },
        )

    async def run_test() -> None:
        client = MeilisearchClient(
            "http://meili.test", "test-key", "book_catalog", transport=httpx.MockTransport(handle)
        )
        try:
            hits, has_next = await client.search(
                "تحلیل دنیا", offset=2, limit=2, matching_strategy="frequency"
            )
        finally:
            await client.aclose()

        assert [hit["id"] for hit in hits] == [11, 12]
        assert has_next is False
        assert requests[0].url.path == "/indexes/book_catalog/search"
        assert requests[0].headers["Authorization"] == "Bearer test-key"
        assert requests[0].read() == (
            b'{"q":"\xd8\xaa\xd8\xad\xd9\x84\xdb\x8c\xd9\x84 '
            b'\xd8\xaf\xd9\x86\xdb\x8c\xd8\xa7","offset":2,"limit":2,'
            b'"matchingStrategy":"frequency","attributesToRetrieve":'
            b'["id","title","display_file_name","caption_preview",'
            b'"file_size","mime_type","media_type","posted_at"]}'
        )

    asyncio.run(run_test())


def test_wait_for_task_polls_until_succeeded():
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = "processing" if calls == 1 else "succeeded"
        return httpx.Response(200, json={"uid": 9, "status": status})

    async def run_test() -> None:
        client = MeilisearchClient(
            "http://meili.test", "test-key", "book_catalog", transport=httpx.MockTransport(handle)
        )
        try:
            task = await client.wait_for_task(9, timeout=1, poll_interval=0)
        finally:
            await client.aclose()

        assert task["status"] == "succeeded"
        assert calls == 2

    asyncio.run(run_test())


def test_delete_documents_uses_numeric_filter_and_rejects_bad_ids():
    requests = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"taskUid": 42})

    async def run_test() -> None:
        client = MeilisearchClient(
            "http://meili.test", "test-key", "book_catalog", transport=httpx.MockTransport(handle)
        )
        try:
            task_uid = await client.delete_documents([10, 20], wait=False)
            with pytest.raises(ValueError):
                await client.delete_documents(["10"], wait=False)
        finally:
            await client.aclose()

        assert task_uid == 42
        assert requests[0].url.path == "/indexes/book_catalog/documents/delete"
        assert requests[0].read() == b'{"filter":"id IN [10,20]"}'

    asyncio.run(run_test())


def test_connection_error_becomes_friendly_backend_unavailable():
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async def run_test() -> None:
        client = MeilisearchClient(
            "http://meili.test", "test-key", "book_catalog", transport=httpx.MockTransport(handle)
        )
        try:
            with pytest.raises(MeilisearchUnavailable, match="unavailable"):
                await client.search("عنوان", offset=0, limit=6)
        finally:
            await client.aclose()

    asyncio.run(run_test())


def test_index_settings_keep_search_fields_order_and_delete_filter():
    assert MEILISEARCH_INDEX_SETTINGS["searchableAttributes"] == [
        "title",
        "file_name",
        "caption",
    ]
    assert MEILISEARCH_INDEX_SETTINGS["rankingRules"][-1] == "posted_at:desc"
    assert "posted_at" in MEILISEARCH_INDEX_SETTINGS["sortableAttributes"]
    assert "id" in MEILISEARCH_INDEX_SETTINGS["filterableAttributes"]
    assert MEILISEARCH_INDEX_SETTINGS["pagination"]["maxTotalHits"] >= 1000


def test_index_stats_reads_document_count():
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/indexes/book_catalog/stats"
        return httpx.Response(200, json={"numberOfDocuments": 25})

    async def run_test() -> None:
        client = MeilisearchClient(
            "http://meili.test", "test-key", "book_catalog", transport=httpx.MockTransport(handle)
        )
        try:
            stats = await client.index_stats()
        finally:
            await client.aclose()

        assert stats["numberOfDocuments"] == 25

    asyncio.run(run_test())


def test_catalog_settings_do_not_require_a_telegram_bot_token():
    settings = CatalogSettings(
        meili_url="http://localhost:7700",
        meili_api_key="local-test-key",
    )

    assert str(settings.meili_url) == "http://localhost:7700/"
    assert settings.meili_api_key.get_secret_value() == "local-test-key"


def test_empty_meilisearch_api_key_disables_optional_client():
    settings = CatalogSettings(meili_api_key="", meili_eval_api_key="")

    assert settings.meili_api_key is None
    assert settings.meili_eval_api_key is None


def test_catalog_repository_accepts_single_word_and_maps_meili_hits():
    class FakeSearch:
        def __init__(self) -> None:
            self.query = None

        async def search(self, query, *, offset, limit):
            self.query = (query, offset, limit)
            return (
                [
                    {
                        "id": 71,
                        "display_file_name": "رمان_کلاسیک.pdf",
                        "caption_preview": "داستان قدیمی",
                        "media_type": "Document",
                        "mime_type": "application/pdf",
                        "file_size": 512,
                    }
                ],
                False,
            )

    async def run_test() -> None:
        search_client = FakeSearch()
        hits, has_next = await book_catalog.search(
            object(), " رمان ", offset=0, limit=6, meilisearch=search_client
        )

        assert search_client.query == ("رمان", 0, 6)
        assert not has_next
        assert hits[0].message_id == 71
        assert hits[0].file_name == "رمان_کلاسیک.pdf"
        assert hits[0].file_size == 512

    asyncio.run(run_test())