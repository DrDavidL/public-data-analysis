import asyncio
import json
import logging

from app.schemas.datasets import DatasetResult
from app.services.ai import chat_mini, extract_json
from app.services.sources.cms import CMSSource
from app.services.sources.datagov import DataGovSource
from app.services.sources.harvard_dataverse import HarvardDataverseSource
from app.services.sources.huggingface import HuggingFaceSource
from app.services.sources.kaggle_source import KaggleSource
from app.services.sources.sdohplace import SDOHPlaceSource
from app.services.sources.worldbank import WorldBankSource

logger = logging.getLogger(__name__)

ALL_SOURCES = [
    DataGovSource(),
    WorldBankSource(),
    KaggleSource(),
    HuggingFaceSource(),
    SDOHPlaceSource(),
    CMSSource(),
    HarvardDataverseSource(),
]


async def _search_source(source: object, query: str, limit: int) -> list[DatasetResult]:
    try:
        return await source.search(query, limit=limit)
    except Exception:
        logger.exception("Search failed for source %s", getattr(source, "source_name", "unknown"))
        return []


async def search_datasets(question: str, limit_per_source: int = 5) -> list[DatasetResult]:
    tasks = [_search_source(src, question, limit_per_source) for src in ALL_SOURCES]
    results_per_source = await asyncio.gather(*tasks)

    all_results: list[DatasetResult] = []
    for source, results in zip(ALL_SOURCES, results_per_source, strict=True):
        name = getattr(source, "source_name", "unknown")
        downloadable_count = sum(1 for r in results if r.download_url)
        logger.info(
            "Source %s returned %d results (%d downloadable)",
            name,
            len(results),
            downloadable_count,
        )
        all_results.extend(results)

    # Only include results with a download URL — showing un-downloadable
    # results is useless since the user can't start an analysis with them.
    downloadable = [r for r in all_results if r.download_url]

    if not downloadable:
        logger.warning("No downloadable results from any source for query=%r", question)
        return []

    # Use GPT-5-mini to rank and describe results
    try:
        ranked = await _rank_with_ai(question, downloadable)
        return ranked[:15]
    except Exception:
        logger.exception("AI ranking failed, returning unranked results")
        return downloadable[:15]


async def _rank_with_ai(question: str, results: list[DatasetResult]) -> list[DatasetResult]:
    summaries = []
    for i, r in enumerate(results[:25]):
        summaries.append(
            {
                "index": i,
                "source": r.source,
                "title": r.title,
                "description": r.description[:300],
                "formats": r.formats,
            }
        )

    messages = [
        {
            "role": "developer",
            "content": (
                "You are a dataset relevance ranker. Given a user's research question and a list "
                "of datasets, rank them by relevance and provide a brief explanation of why each "
                "dataset is relevant. Respond with JSON only.\n\n"
                "Output format: "
                '{"ranked": [{"index": <int>, '
                '"relevance": <str 1-2 sentences>}, ...]}\n'
                "Return the top 15 most relevant datasets, ordered by relevance."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nDatasets:\n{json.dumps(summaries)}",
        },
    ]

    response_text = await chat_mini(messages, max_tokens=4096)

    ranking = extract_json(response_text)

    ranked_results = []
    for item in ranking.get("ranked", []):
        idx = item["index"]
        if 0 <= idx < len(results):
            result = results[idx]
            result.ai_description = item.get("relevance", "")
            ranked_results.append(result)

    # Add any results not included in ranking
    ranked_indices = {item["index"] for item in ranking.get("ranked", [])}
    for i, r in enumerate(results):
        if i not in ranked_indices and len(ranked_results) < 15:
            ranked_results.append(r)

    return ranked_results
