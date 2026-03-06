"""FRED (Federal Reserve Economic Data) API adapter.

Uses the FRED API at api.stlouisfed.org to search for and download
economic time series data. Requires a free API key from
https://fred.stlouisfed.org/docs/api/api_key.html
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

BASE_URL = "https://api.stlouisfed.org/fred"
TIMEOUT = 20.0


class FREDSource:
    source_name: str = "fred"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search FRED for economic data series matching *query*."""
        api_key = settings.fred_api_key
        if not api_key:
            logger.debug("FRED API key not configured, skipping")
            return []

        params: dict[str, str | int] = {
            "search_text": query,
            "api_key": api_key,
            "file_type": "json",
            "limit": limit,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(f"{BASE_URL}/series/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("FRED search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for series in data.get("seriess", []):
            series_id = series.get("id", "")
            if not series_id:
                continue
            title = series.get("title", "")
            notes = series.get("notes", "") or ""

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=series_id,
                    title=title,
                    description=notes[:500],
                    formats=["JSON"],
                    download_url=(
                        f"{BASE_URL}/series/observations"
                        f"?series_id={series_id}&api_key={api_key}&file_type=json"
                    ),
                    metadata={
                        k: v
                        for k, v in {
                            "frequency": series.get("frequency"),
                            "units": series.get("units"),
                            "seasonal_adjustment": series.get("seasonal_adjustment"),
                            "observation_start": series.get("observation_start"),
                            "observation_end": series.get("observation_end"),
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        api_key = settings.fred_api_key
        if not api_key or not dataset_id:
            return None
        return (
            f"{BASE_URL}/series/observations"
            f"?series_id={dataset_id}&api_key={api_key}&file_type=json"
        )

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download FRED series observations as JSON."""
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{dataset_id}.json"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()

            observations = payload.get("observations", [])
            if not observations:
                logger.warning("FRED returned no observations for %s", dataset_id)
                return None

            dest.write_text(json.dumps(observations, ensure_ascii=False))
            return dest
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("FRED download failed for %s: %s", dataset_id, exc)
            return None
