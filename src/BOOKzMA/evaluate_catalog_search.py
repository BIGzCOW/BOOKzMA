import asyncio
import json
import logging
import math
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

from BOOKzMA.config import CatalogSettings
from BOOKzMA.services.catalog_text import build_search_document, normalize_catalog_text
from BOOKzMA.services.meilisearch import MeilisearchClient

log = logging.getLogger(__name__)
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "catalog_search_cases.json"


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def _fixture_documents(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    documents = []
    for source in fixture["documents"]:
        documents.append(
            build_search_document(
                message_id=source["message_id"],
                file_name=source.get("file_name"),
                caption_preview=source.get("caption_preview"),
                caption_search=source.get("caption_search", ""),
                file_size=source.get("file_size"),
                mime_type=source.get("mime_type"),
                media_type=source.get("media_type"),
                posted_at=source.get("posted_at"),
            )
        )
    return documents


async def evaluate_catalog_search(settings: CatalogSettings) -> dict[str, Any]:
    if settings.meili_url is None or settings.meili_eval_api_key is None:
        raise RuntimeError("MEILI_URL and MEILI_EVAL_API_KEY are required for evaluation")
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    scenarios = fixture["scenarios"]
    index_name = f"{settings.meili_index_name}_eval_{uuid.uuid4().hex[:12]}"
    client = MeilisearchClient(
        str(settings.meili_url),
        settings.meili_eval_api_key.get_secret_value(),
        index_name,
        timeout=settings.meili_timeout_seconds,
    )
    try:
        await client.ensure_index()
        await client.add_documents(_fixture_documents(fixture), task_timeout=600)
        measurements: dict[str, dict[str, float | int]] = {}
        for strategy in ("frequency", "last"):
            latencies: list[float] = []
            successful_queries = 0
            for scenario in scenarios:
                started = time.perf_counter()
                hits, _has_next = await client.search(
                    normalize_catalog_text(scenario["query"]),
                    offset=0,
                    limit=10,
                    matching_strategy=strategy,
                )
                latencies.append((time.perf_counter() - started) * 1000)
                hit_ids = {hit.get("id") for hit in hits}
                if hit_ids.intersection(scenario["expected_ids"]):
                    successful_queries += 1
            measurements[strategy] = {
                "top10_queries": successful_queries,
                "query_count": len(scenarios),
                "top10_percent": round(100 * successful_queries / len(scenarios), 2),
                "p50_ms": round(statistics.median(latencies), 2),
                "p95_ms": _percentile(latencies, 0.95),
            }
        selected = max(
            measurements,
            key=lambda strategy: (
                measurements[strategy]["top10_percent"],
                -measurements[strategy]["p95_ms"],
                strategy == "frequency",
            ),
        )
        return {"strategies": measurements, "selected_strategy": selected}
    finally:
        try:
            await client.delete_index()
        except Exception as error:
            log.warning(
                "temporary catalog evaluation index cleanup failed (%s)",
                type(error).__name__,
            )
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        report = asyncio.run(evaluate_catalog_search(CatalogSettings()))
    except Exception as error:
        log.error("catalog search evaluation failed (%s)", type(error).__name__)
        raise SystemExit(1) from error
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()