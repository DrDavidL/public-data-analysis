"""HUD GIS Open Data (ArcGIS Hub) adapter.

Uses the ArcGIS Hub Search API v3 at hudgis-hud.opendata.arcgis.com.
Filtered to CSV-downloadable datasets only.
No authentication required.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

SEARCH_URL = "https://hudgis-hud.opendata.arcgis.com/api/v3/datasets"
TIMEOUT = 20.0

# CSV format filter values returned by the ArcGIS Hub API
_CSV_FORMATS = {"csv", "text/csv"}


class HUDSource:
    source_name: str = "hud"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search HUD GIS Open Data for CSV-downloadable datasets."""
        params: dict[str, str | int] = {
            "q": query,
            "page[size]": limit * 3,  # over-fetch to compensate for CSV filtering
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("HUD search failed for query=%r: %s", query, exc)
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
            # Strip HTML tags from description
            if "<" in description:
                import re

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
        """Fetch the CSV download URL for a specific HUD dataset."""
        if not dataset_id:
            return None

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(f"{SEARCH_URL}/{dataset_id}")
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("HUD get_download_url failed for %s: %s", dataset_id, exc)
            return None

        attrs = payload.get("data", {}).get("attributes", {})
        return _pick_csv_url(attrs) if isinstance(attrs, dict) else None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download a HUD dataset as CSV."""
        download_url = await self.get_download_url(dataset_id)
        if not download_url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:100]
        dest = dest_dir / f"{safe_name}.csv"

        try:
            async with httpx.AsyncClient(
                timeout=60,
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    with dest.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("HUD download failed for %s: %s", dataset_id, exc)
            return None

        return dest


def _pick_csv_url(attrs: dict) -> str | None:
    """Extract a CSV download URL from ArcGIS Hub dataset attributes.

    The Hub API exposes download links under ``recordCount``-bearing entries
    or via a ``url`` field. We look for explicit CSV download links first.
    """
    # Hub v3 often provides a direct CSV download link
    download_link = attrs.get("downloadLink")
    if download_link and "csv" in download_link.lower():
        return download_link

    # Check the accessInformation / hub download links
    hub_url = attrs.get("url", "")
    if hub_url:
        # ArcGIS Hub convention: append /csv to the landing page URL
        csv_url = hub_url.rstrip("/")
        if "/datasets/" in csv_url:
            return f"{csv_url}.csv"

    # Check structuredLicense or other nested fields for download URLs
    source_url = attrs.get("sourceUrl") or attrs.get("contentUrl") or ""
    if source_url and "FeatureServer" in source_url:
        # ArcGIS Feature Service — can request CSV via query
        return f"{source_url}/query?where=1%3D1&outFields=*&f=csv"

    return None
