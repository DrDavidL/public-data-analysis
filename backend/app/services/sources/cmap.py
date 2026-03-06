"""CMAP Data Hub (ArcGIS Hub) adapter.

Uses the ArcGIS Hub Search API v3 at datahub.cmap.illinois.gov.
No authentication required. Covers Chicago metropolitan area
planning data (transportation, housing, demographics, environment).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

SEARCH_URL = "https://datahub.cmap.illinois.gov/api/v3/datasets"
TIMEOUT = 20.0


class CMAPSource:
    source_name: str = "cmap"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search CMAP Data Hub for datasets."""
        params: dict[str, str | int] = {
            "q": query,
            "page[size]": limit * 3,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("CMAP search failed for query=%r: %s", query, exc)
            return []

        items = payload.get("data", [])
        if not isinstance(items, list):
            return []

        results: list[DatasetResult] = []
        for item in items:
            if len(results) >= limit:
                break

            attrs = item.get("attributes", {})
            if not isinstance(attrs, dict):
                continue

            csv_url = _pick_csv_url(attrs)
            if not csv_url:
                continue

            dataset_id = item.get("id", "")
            title = attrs.get("name", "") or attrs.get("title", "")
            description = attrs.get("description", "") or ""
            if "<" in description:
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=dataset_id,
                    title=title,
                    description=description[:500],
                    formats=["CSV"],
                    download_url=csv_url,
                    metadata={
                        k: v
                        for k, v in {
                            "tags": attrs.get("tags"),
                            "source": attrs.get("source"),
                            "updatedAt": attrs.get("updatedAt"),
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(f"{SEARCH_URL}/{dataset_id}")
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("CMAP get_download_url failed for %s: %s", dataset_id, exc)
            return None

        attrs = payload.get("data", {}).get("attributes", {})
        return _pick_csv_url(attrs) if isinstance(attrs, dict) else None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        download_url = await self.get_download_url(dataset_id)
        if not download_url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:100]
        dest = dest_dir / f"{safe_name}.csv"

        try:
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                async with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    with dest.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("CMAP download failed for %s: %s", dataset_id, exc)
            return None

        return dest


def _pick_csv_url(attrs: dict) -> str | None:
    """Extract a CSV download URL from ArcGIS Hub dataset attributes."""
    download_link = attrs.get("downloadLink")
    if download_link and "csv" in download_link.lower():
        return download_link

    hub_url = attrs.get("url", "")
    if hub_url:
        csv_url = hub_url.rstrip("/")
        if "/datasets/" in csv_url:
            return f"{csv_url}.csv"

    source_url = attrs.get("sourceUrl") or attrs.get("contentUrl") or ""
    if source_url and "FeatureServer" in source_url:
        return f"{source_url}/query?where=1%3D1&outFields=*&f=csv"

    return None
