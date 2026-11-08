import asyncio
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx


MAX_TOTAL_HITS = 10_000

MEILISEARCH_INDEX_SETTINGS: dict[str, Any] = {
    "searchableAttributes": ["title", "file_name", "caption"],
    "displayedAttributes": [
        "id",
        "title",
        "display_file_name",
        "caption_preview",
        "file_size",
        "mime_type",
        "media_type",
        "posted_at",
    ],
    "rankingRules": [
        "words",
        "typo",
        "proximity",
        "attributeRank",
        "sort",
        "wordPosition",
        "exactness",
        "posted_at:desc",
    ],
    "sortableAttributes": ["posted_at"],
    "filterableAttributes": ["id"],
    "typoTolerance": {
        "enabled": True,
        "minWordSizeForTypos": {"oneTypo": 5, "twoTypos": 9},
        "disableOnNumbers": True,
    },
    "stopWords": ["و", "در", "از", "به", "با", "را", "که", "این", "آن", "برای"],
    "synonyms": {},
    "pagination": {"maxTotalHits": MAX_TOTAL_HITS},
}


class MeilisearchError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MeilisearchUnavailable(MeilisearchError):
    pass


class MeilisearchClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        index_name: str,
        *,
        timeout: float = 2.0,
        matching_strategy: str = "frequency",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.index_name = index_name
        self.matching_strategy = matching_strategy
        self._index_path = quote(index_name, safe="")
        self._client = httpx.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, json=json, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise MeilisearchUnavailable("Meilisearch request timed out") from error
        except httpx.TransportError as error:
            raise MeilisearchUnavailable("Meilisearch is unavailable") from error
        except httpx.HTTPStatusError as error:
            raise MeilisearchError(
                f"Meilisearch returned HTTP {error.response.status_code}",
                status_code=error.response.status_code,
            ) from error
        if not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as error:
            raise MeilisearchError("Meilisearch returned invalid JSON") from error
        if not isinstance(payload, dict):
            raise MeilisearchError("Meilisearch returned an unexpected response")
        return payload

    async def search(
        self,
        query: str,
        *,
        offset: int,
        limit: int,
        matching_strategy: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        if offset < 0 or limit < 1:
            raise ValueError("offset must be non-negative and limit must be positive")
        if offset >= MAX_TOTAL_HITS:
            return [], False
        limit = min(limit, MAX_TOTAL_HITS - offset)
        payload = await self._request(
            "POST",
            f"/indexes/{self._index_path}/search",
            json={
                "q": query,
                "offset": offset,
                "limit": limit,
                "matchingStrategy": matching_strategy or self.matching_strategy,
                "attributesToRetrieve": MEILISEARCH_INDEX_SETTINGS["displayedAttributes"],
            },
        )
        hits = payload.get("hits")
        if not isinstance(hits, list):
            raise MeilisearchError("Meilisearch returned malformed search results")
        estimated_total = payload.get("estimatedTotalHits", offset + len(hits))
        if not isinstance(estimated_total, int):
            estimated_total = offset + len(hits)
        return hits, offset + len(hits) < estimated_total

    async def index_stats(self) -> dict[str, Any]:
        return await self._request("GET", f"/indexes/{self._index_path}/stats")

    async def delete_index(self, *, task_timeout: float = 300.0) -> None:
        try:
            await self._request("GET", f"/indexes/{self._index_path}")
        except MeilisearchError as error:
            if error.status_code == 404:
                return
            raise
        task = await self._request("DELETE", f"/indexes/{self._index_path}")
        await self.wait_for_task(task["taskUid"], timeout=task_timeout)

    async def ensure_index(self, *, task_timeout: float = 300.0) -> None:
        try:
            await self._request("GET", f"/indexes/{self._index_path}")
        except MeilisearchError as error:
            if error.status_code != 404:
                raise
            task = await self._request(
                "POST", "/indexes", json={"uid": self.index_name, "primaryKey": "id"}
            )
            await self.wait_for_task(task["taskUid"], timeout=task_timeout)

        task = await self._request(
            "PATCH",
            f"/indexes/{self._index_path}/settings",
            json=MEILISEARCH_INDEX_SETTINGS,
        )
        await self.wait_for_task(task["taskUid"], timeout=task_timeout)

    async def add_documents(
        self,
        documents: Sequence[Mapping[str, Any]],
        *,
        wait: bool = True,
        task_timeout: float = 300.0,
    ) -> int | None:
        if not documents:
            return None
        task = await self._request(
            "POST",
            f"/indexes/{self._index_path}/documents",
            params={"primaryKey": "id"},
            json=list(documents),
        )
        task_uid = task.get("taskUid")
        if not isinstance(task_uid, int):
            raise MeilisearchError("Meilisearch did not return a task UID")
        if wait:
            await self.wait_for_task(task_uid, timeout=task_timeout)
        return task_uid

    async def delete_documents(
        self,
        document_ids: Sequence[int],
        *,
        wait: bool = True,
        task_timeout: float = 300.0,
    ) -> int | None:
        if not document_ids:
            return None
        if any(
            not isinstance(document_id, int) or document_id <= 0
            for document_id in document_ids
        ):
            raise ValueError("document IDs must be positive integers")
        ids = ",".join(str(document_id) for document_id in document_ids)
        task = await self._request(
            "POST",
            f"/indexes/{self._index_path}/documents/delete",
            json={"filter": f"id IN [{ids}]"},
        )
        task_uid = task.get("taskUid")
        if not isinstance(task_uid, int):
            raise MeilisearchError("Meilisearch did not return a task UID")
        if wait:
            await self.wait_for_task(task_uid, timeout=task_timeout)
        return task_uid

    async def wait_for_task(
        self,
        task_uid: int,
        *,
        timeout: float = 300.0,
        poll_interval: float = 0.25,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            task = await self._request("GET", f"/tasks/{task_uid}")
            status = task.get("status")
            if status == "succeeded":
                return task
            if status in {"failed", "canceled"}:
                error = task.get("error")
                code = error.get("code") if isinstance(error, dict) else "unknown"
                raise MeilisearchError(f"Meilisearch task {status}: {code}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MeilisearchUnavailable("Meilisearch task timed out")
            await asyncio.sleep(min(poll_interval, remaining))