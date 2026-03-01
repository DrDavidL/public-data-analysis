"""CMS (Centers for Medicare & Medicaid Services) DKAN API adapter.

Uses the open data.cms.gov DKAN metastore and datastore APIs.
No authentication required for public data.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

METASTORE_URL = "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items"
DATASTORE_DOWNLOAD_URL = (
    "https://data.cms.gov/provider-data/api/1/datastore/query/{dataset_id}/0"
    "/download?format=csv"
)
TIMEOUT = 20.0


class CMSSource:
    source_name: str = "cms"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search CMS Provider Data Catalog via DKAN metastore."""
        params = {
            "fulltext": query,
            "page-size": limit,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(METASTORE_URL, params=params)
                resp.raise_for_status()
                items = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("CMS search failed for query=%r: %s", query, exc)
            return []

        if not isinstance(items, list):
            return []

        results: list[DatasetResult] = []
        for item in items[:limit]:
            dataset_id = item.get("identifier", "")
            title = item.get("title", "")
            description = item.get("description", "")

            # Extract download URL from distributions
            download_url = _pick_download_url(item)

            # Extract formats
            formats = _extract_formats(item)

            # Extract theme/keyword metadata
            theme = item.get("theme", [])
            keyword = item.get("keyword", [])
            modified = item.get("modified", "")

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=dataset_id,
                    title=title,
                    description=description[:500] if description else "",
                    formats=formats,
                    download_url=download_url,
                    metadata={
                        k: v
                        for k, v in {
                            "theme": theme or None,
                            "keyword": keyword or None,
                            "modified": modified or None,
                        }.items()
                        if v is not None
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return a CSV download URL for the given CMS dataset ID."""
        if not dataset_id:
            return None
        return DATASTORE_DOWNLOAD_URL.format(dataset_id=dataset_id)

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download a CMS dataset as CSV."""
        download_url = await self.get_download_url(dataset_id)
        if not download_url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:100]
        dest = dest_dir / f"{safe_name}.csv"

        try:
            async with httpx.AsyncClient(
                timeout=60, follow_redirects=True,
            ) as client:
                async with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    with dest.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "CMS download failed for %s: %s", dataset_id, exc,
            )
            return None

        return dest


def _pick_download_url(item: dict) -> str | None:
    """Extract the best CSV/JSON download URL from a DKAN dataset item."""
    distributions = item.get("distribution", [])
    if not isinstance(distributions, list):
        return None

    for preferred in ("text/csv", "application/json"):
        for dist in distributions:
            media_type = (dist.get("mediaType") or "").lower()
            url = dist.get("downloadURL") or dist.get("accessURL")
            if media_type == preferred and url:
                return url

    # Fallback: first distribution with any download URL
    for dist in distributions:
        url = dist.get("downloadURL") or dist.get("accessURL")
        if url:
            return url

    return None


def _extract_formats(item: dict) -> list[str]:
    """Extract available formats from distribution metadata."""
    formats: list[str] = []
    seen: set[str] = set()
    for dist in item.get("distribution", []):
        media_type = (dist.get("mediaType") or "").lower()
        fmt = ""
        if "csv" in media_type:
            fmt = "CSV"
        elif "json" in media_type:
            fmt = "JSON"
        elif "xml" in media_type:
            fmt = "XML"
        if fmt and fmt not in seen:
            seen.add(fmt)
            formats.append(fmt)
    return formats
