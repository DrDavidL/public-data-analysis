import asyncio
import json
import logging

from app.schemas.datasets import DatasetResult
from app.services.ai import chat_mini, extract_json
from app.services.source_index import SourceIndex
from app.services.sources.bls import BLSSource
from app.services.sources.census import CensusSource
from app.services.sources.cmap import CMAPSource
from app.services.sources.cms import CMSSource
from app.services.sources.datagov import DataGovSource
from app.services.sources.eia import EIASource
from app.services.sources.fred import FREDSource
from app.services.sources.harvard_dataverse import HarvardDataverseSource
from app.services.sources.hud import HUDSource
from app.services.sources.huggingface import HuggingFaceSource
from app.services.sources.kaggle_source import KaggleSource
from app.services.sources.oecd import OECDSource
from app.services.sources.owid import OWIDSource
from app.services.sources.sdohplace import SDOHPlaceSource
from app.services.sources.vdem import VDemSource
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
    HUDSource(),
    BLSSource(),
    FREDSource(),
    CMAPSource(),
    CensusSource(),
    OWIDSource(),
    OECDSource(),
    VDemSource(),
    EIASource(),
]

_source_index = SourceIndex()


async def _search_source(source: object, query: str, limit: int) -> list[DatasetResult]:
    try:
        return await source.search(query, limit=limit)
    except Exception:
        logger.exception("Search failed for source %s", getattr(source, "source_name", "unknown"))
        return []


async def _refine_query(question: str) -> str:
    """Use AI to extract concise search keywords from a natural language question."""
    messages = [
        {
            "role": "developer",
            "content": (
                "Extract 3-6 concise search keywords from the user's research question. "
                "Return ONLY the keywords separated by spaces, no explanation. "
                "Focus on the core subject/topic, not filler words."
            ),
        },
        {"role": "user", "content": question},
    ]
    try:
        refined = await chat_mini(messages, max_tokens=500)
        refined = refined.strip().strip('"').strip("'")
        if refined:
            logger.info("Refined query: %r -> %r", question, refined)
            return refined
    except Exception:
        logger.debug("Query refinement failed, using original question")
    return question


async def search_datasets(
    question: str,
    limit_per_source: int = 5,
    sources: list[str] | None = None,
) -> list[DatasetResult]:
    # Refine the natural language question into search-friendly keywords
    search_query = await _refine_query(question)

    # Refresh cross-source index (no-op if cache is fresh)
    await _source_index.refresh()

    # Filter to selected sources (None = all)
    active_sources = ALL_SOURCES
    if sources is not None:
        allowed = set(sources)
        active_sources = [s for s in ALL_SOURCES if s.source_name in allowed]

    tasks = [_search_source(src, search_query, limit_per_source) for src in active_sources]
    results_per_source = await asyncio.gather(*tasks)

    all_results: list[DatasetResult] = []
    for source, results in zip(active_sources, results_per_source, strict=True):
        name = getattr(source, "source_name", "unknown")
        downloadable_count = sum(1 for r in results if r.download_url)
        logger.info(
            "Source %s returned %d results (%d downloadable)",
            name,
            len(results),
            downloadable_count,
        )
        all_results.extend(results)

    # Merge any cross-source index hits not already present
    existing_ids = {(r.source, r.id) for r in all_results}
    index_hits = _source_index.search(question, limit=10)
    for hit in index_hits:
        if (hit.source, hit.id) not in existing_ids:
            all_results.append(
                DatasetResult(
                    source=hit.source,
                    id=hit.id,
                    title=hit.title,
                    description=hit.description,
                    formats=[],
                    download_url=None,
                    metadata={},
                )
            )

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
                "of datasets, score each by relevance (0.0-1.0) and provide a brief explanation. "
                "ONLY include datasets with score >= 0.4 that are genuinely useful for answering "
                "the question. Omit datasets that merely share a keyword but aren't actually "
                "relevant. Respond with JSON only.\n\n"
                "Output format: "
                '{"ranked": [{"index": <int>, "score": <float>, '
                '"relevance": <str 1-2 sentences>}, ...]}\n'
                "Return up to 15 relevant datasets, ordered by score descending."
            ),
        },
        {
            "role": "user",
            "content": f"Question: {question}\n\nDatasets:\n{json.dumps(summaries)}",
        },
    ]

    response_text = await chat_mini(messages, max_tokens=4096, json_mode=True)

    ranking = extract_json(response_text)

    ranked_results = []
    for item in ranking.get("ranked", []):
        idx = item.get("index", -1)
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        if 0 <= idx < len(results) and score >= 0.4:
            result = results[idx]
            result.ai_description = item.get("relevance", "")
            ranked_results.append(result)

    # Fallback: if ranking filtered out everything, return unranked results
    if not ranked_results and results:
        logger.warning("AI ranking returned no results above threshold; returning unranked")
        return results[:15]

    return ranked_results
