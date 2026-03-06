"""Census.gov API adapter.

Uses the Census Data API to search available datasets and download data.
API key is recommended (free at https://api.census.gov/data/key_signup.html)
but not strictly required for low-volume use.

Key datasets:
- ACS (American Community Survey) 1-year and 5-year
- Decennial Census
- Population Estimates
- County Business Patterns
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

DISCOVERY_URL = "https://api.census.gov/data.json"
TIMEOUT = 20.0

# Cache the dataset catalog (changes rarely)
_CATALOG_CACHE: list[dict] = []
_CATALOG_TIMESTAMP: float = 0.0
_CATALOG_TTL = 86400  # 24 hours


class CensusSource:
    source_name: str = "census"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search Census API datasets by keyword matching against the catalog."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        catalog = await self._get_catalog()
        if not catalog:
            return []

        scored: list[tuple[int, dict]] = []
        for ds in catalog:
            title = ds.get("title", "").lower()
            description = ds.get("description", "").lower()
            text = f"{title} {description}"
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ds))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ds in scored[:limit]:
            dist = ds.get("distribution") or []
            api_url = dist[0].get("accessURL", "") if dist else ""
            if not api_url:
                api_url = ds.get("accessURL", "")
            if not api_url:
                continue

            dataset_id = ds.get("identifier", "") or api_url
            title = ds.get("title", "")
            description = ds.get("description", "")

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=dataset_id,
                    title=title,
                    description=description[:500] if description else "",
                    formats=["JSON"],
                    download_url=api_url,
                    metadata={
                        k: v
                        for k, v in {
                            "vintage": ds.get("c_vintage"),
                            "geographic_coverage": ds.get("c_geographyLink"),
                            "modified": ds.get("modified"),
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Look up the API URL for a dataset by its identifier."""
        if not dataset_id:
            return None

        # If the ID is already a URL, use it directly
        if dataset_id.startswith("http"):
            return dataset_id

        catalog = await self._get_catalog()
        for ds in catalog:
            if ds.get("identifier") == dataset_id:
                dist = ds.get("distribution", [{}])
                if dist:
                    return dist[0].get("accessURL")
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download Census data as JSON."""
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.split("/")[-1] if "/" in dataset_id else dataset_id
        safe_name = safe_name.replace("?", "_").replace("&", "_")[:100]
        dest = dest_dir / f"census_{safe_name}.json"

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # Census API returns data as a JSON array of arrays:
                # [["header1","header2",...], ["val1","val2",...], ...]
                # We request a basic query to get state-level data.
                params: dict[str, str] = {}
                if "?" not in url:
                    # No query specified — request all variables for all states
                    params = {"get": "NAME", "for": "state:*"}

                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            if not data or not isinstance(data, list) or len(data) < 2:
                logger.warning("Census API returned insufficient data for %s", dataset_id)
                return None

            # Convert array-of-arrays to array-of-objects
            headers = [str(h) for h in data[0]]
            records = [{headers[i]: row[i] for i in range(len(headers))} for row in data[1:]]

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("Census download failed for %s: %s", dataset_id, exc)
            return None

    @staticmethod
    async def _get_catalog() -> list[dict]:
        """Fetch and cache the Census API dataset catalog."""
        global _CATALOG_CACHE, _CATALOG_TIMESTAMP  # noqa: PLW0603

        now = time.monotonic()
        if _CATALOG_CACHE and (now - _CATALOG_TIMESTAMP) < _CATALOG_TTL:
            return _CATALOG_CACHE

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(DISCOVERY_URL)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.exception("Census catalog fetch failed, using stale cache")
            return _CATALOG_CACHE

        datasets = data.get("dataset", [])
        if datasets:
            _CATALOG_CACHE = datasets
            _CATALOG_TIMESTAMP = now
            logger.info("Census catalog refreshed (%d datasets)", len(datasets))

        return _CATALOG_CACHE
