from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords as _extract_keywords

logger = logging.getLogger(__name__)

CATALOG_URL = "https://datacatalogapi.worldbank.org/ddhxext/DatasetList"
INDICATOR_URL = "https://api.worldbank.org/v2/indicator"
TIMEOUT = 15.0
DOWNLOAD_TIMEOUT = 60.0  # More generous timeout for paginated downloads


class WorldBankSource:
    source_name: str = "worldbank"

    # Class-level indicator cache shared across instances.
    _indicators_cache: list[dict] = []
    _indicators_timestamp: float = 0.0
    INDICATORS_CACHE_TTL = 86400  # 24 hours — indicators change very rarely

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search the World Bank Data Catalog and indicator APIs."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            catalog_results = await _fetch_catalog(client, query, limit)
            indicator_results = await _fetch_indicators(client, query, limit)

        results = catalog_results + indicator_results
        return results[:limit]

    @classmethod
    async def _get_all_indicators(cls, client: httpx.AsyncClient) -> list[dict]:
        """Return all WDI indicators, using a 24-hour in-memory cache."""
        now = time.monotonic()
        if cls._indicators_cache and (now - cls._indicators_timestamp) < cls.INDICATORS_CACHE_TTL:
            logger.debug("World Bank indicators cache hit (%d entries)", len(cls._indicators_cache))
            return cls._indicators_cache

        try:
            resp = await client.get(
                INDICATOR_URL,
                params={"format": "json", "per_page": 1000, "source": 2},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.exception("World Bank indicator fetch failed, using stale cache")
            return cls._indicators_cache  # stale is better than empty

        if not isinstance(payload, list) or len(payload) < 2:
            return cls._indicators_cache

        indicators: list[dict] = payload[1] or []
        if indicators:
            cls._indicators_cache = indicators
            cls._indicators_timestamp = now
            logger.info("World Bank indicators cache refreshed (%d entries)", len(indicators))

        return indicators

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return a download URL for a dataset or indicator by ID."""
        # If the ID looks like an indicator code (short alphanumeric), build
        # the indicator API URL directly.
        if (
            dataset_id
            and len(dataset_id) < 40
            and dataset_id.replace(".", "").replace("_", "").isalnum()
        ):
            return (
                f"https://api.worldbank.org/v2/country/all/indicator/"
                f"{dataset_id}?format=json&per_page=10000"
            )
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download indicator data as JSON to *dest_dir*.

        The World Bank API returns ``[{pagination}, [{record}, ...]]``.
        We extract just the data array so DuckDB's ``read_json_auto``
        can parse it as a flat array of objects.
        """
        url = await self.get_download_url(dataset_id)
        if url is None:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{dataset_id}.json"

        try:
            all_records: list[dict] = []
            page = 1
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT) as client:
                while True:
                    page_url = f"{url}&page={page}"
                    resp = await client.get(page_url)
                    resp.raise_for_status()
                    payload = resp.json()

                    # Unwrap the [pagination, data_array] envelope
                    if (
                        isinstance(payload, list)
                        and len(payload) >= 2
                        and isinstance(payload[1], list)
                    ):
                        all_records.extend(payload[1])
                        pagination = payload[0]
                        total_pages = int(pagination.get("pages", 1))
                        if page >= total_pages:
                            break
                        page += 1
                    else:
                        # Not the expected format — save as-is
                        all_records = payload if isinstance(payload, list) else [payload]
                        break

            dest.write_text(json.dumps(all_records, ensure_ascii=False))
            return dest
        except (httpx.HTTPError, OSError, ValueError):
            logger.exception("Failed to download dataset %s", dataset_id)
            return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _fetch_catalog(client: httpx.AsyncClient, query: str, limit: int) -> list[DatasetResult]:
    """Search the World Bank Data Catalog API using keyword-based OData filter."""
    keywords = _extract_keywords(query)
    if not keywords:
        return []

    # Build OData filter: match ANY keyword in dataset name
    safe = [kw.replace("'", "''") for kw in keywords[:4]]
    odata_filter = " or ".join(f"contains(name,'{kw}')" for kw in safe)

    try:
        resp = await client.get(CATALOG_URL, params={"$filter": odata_filter})
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("World Bank catalog search failed for query=%s", query)
        return []

    datasets: list[dict] = []
    if isinstance(data, dict):
        datasets = data.get("data", data.get("value", []))
    elif isinstance(data, list):
        datasets = data

    results: list[DatasetResult] = []
    for ds in datasets:
        if len(results) >= limit:
            break

        download_url = ds.get("url") or ds.get("distribution_url") or None
        # Skip catalog entries without a download URL — they're just metadata
        if not download_url:
            continue

        ds_id = str(ds.get("dataset_unique_id") or ds.get("nid") or ds.get("id", ""))
        title = ds.get("name") or ds.get("title") or ""
        description = (
            ds.get("description") or ds.get("identification", {}).get("abstract", "") or ""
        )
        formats = _extract_formats(ds)

        results.append(
            DatasetResult(
                source="worldbank",
                id=ds_id,
                title=title,
                description=description[:500] if description else "",
                formats=formats,
                download_url=download_url,
                metadata={
                    k: v
                    for k, v in {
                        "topics": ds.get("topics"),
                        "country": ds.get("country"),
                        "last_updated": ds.get("last_updated_date"),
                    }.items()
                    if v is not None
                },
            )
        )
    return results


async def _fetch_indicators(
    client: httpx.AsyncClient, query: str, limit: int
) -> list[DatasetResult]:
    """Search the World Bank Indicators API (source 2 = World Development Indicators)."""
    keywords = _extract_keywords(query)
    if not keywords:
        return []

    indicators = await WorldBankSource._get_all_indicators(client)

    # Score each indicator by how many keywords match its name or description.
    # Require at least half the keywords to match (minimum 1) to avoid
    # flooding results with loosely-related indicators.
    min_hits = max(1, len(keywords) // 2)
    scored: list[tuple[int, dict]] = []
    for ind in indicators:
        name_lower = ind.get("name", "").lower()
        note_lower = ind.get("sourceNote", "").lower()
        text = f"{name_lower} {note_lower}"
        hits = sum(1 for kw in keywords if kw in text)
        if hits >= min_hits:
            scored.append((hits, ind))

    # Sort by number of keyword hits (descending)
    scored.sort(key=lambda x: x[0], reverse=True)

    matched: list[DatasetResult] = []
    for _hits, ind in scored[:limit]:
        name = ind.get("name", "")
        source_note = ind.get("sourceNote", "")
        code = ind.get("id", "")

        matched.append(
            DatasetResult(
                source="worldbank",
                id=code,
                title=name,
                description=source_note[:500] if source_note else "",
                formats=["json"],
                download_url=(
                    f"https://api.worldbank.org/v2/country/all/indicator/"
                    f"{code}?format=json&per_page=10000"
                ),
                metadata={
                    k: v
                    for k, v in {
                        "source": ind.get("source", {}).get("value"),
                        "topics": [t.get("value") for t in ind.get("topics", []) if t.get("value")]
                        or None,
                    }.items()
                    if v is not None
                },
            )
        )

    return matched


def _extract_formats(ds: dict) -> list[str]:
    """Pull available format strings from a catalog dataset entry."""
    formats: list[str] = []
    for resource in ds.get("Resources", ds.get("resources", [])):
        fmt = resource.get("format") or resource.get("file_type") or ""
        if fmt and fmt not in formats:
            formats.append(fmt)
    if not formats:
        dist = ds.get("distribution", [])
        if isinstance(dist, list):
            for d in dist:
                fmt = d.get("format", "")
                if fmt and fmt not in formats:
                    formats.append(fmt)
    return formats
