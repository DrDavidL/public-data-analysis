"""Our World in Data (OWID) source adapter.

Searches the OWID catalog via their public search API and downloads
datasets as CSV files from the grapher endpoint. No API key required.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

SEARCH_URL = "https://ourworldindata.org/api/search"
TIMEOUT = 15.0
DOWNLOAD_TIMEOUT = 60.0


class OWIDSource:
    source_name: str = "owid"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search Our World in Data charts matching *query*."""
        params: dict[str, str | int] = {
            "q": query,
            "type": "charts",
            "page": 0,
            "hitsPerPage": limit,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("OWID search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for hit in data.get("results", []):
            slug = hit.get("slug", "")
            if not slug:
                continue
            title = hit.get("title", slug)
            subtitle = hit.get("subtitle", "") or ""
            available_entities = hit.get("availableEntities", [])

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=slug,
                    title=title,
                    description=subtitle[:500],
                    formats=["CSV"],
                    download_url=f"https://ourworldindata.org/grapher/{slug}.csv",
                    metadata={
                        k: v
                        for k, v in {
                            "chart_type": hit.get("type"),
                            "countries": available_entities[:20] if available_entities else None,
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return f"https://ourworldindata.org/grapher/{dataset_id}.csv"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download an OWID grapher dataset as CSV."""
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{dataset_id}.csv"

        try:
            async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            dest.write_bytes(resp.content)
            return dest
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("OWID download failed for %s: %s", dataset_id, exc)
            return None
