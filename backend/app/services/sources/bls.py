"""BLS (Bureau of Labor Statistics) Public Data API adapter.

Uses the BLS API v2 at api.bls.gov for time series data.
An API key (registration at https://www.bls.gov/developers/) enables higher
rate limits but is not required for basic access.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
TIMEOUT = 20.0

# Curated popular BLS series — these cover the most common queries.
# The BLS API doesn't have a search endpoint, so we match keywords
# against this index and also fall back to data.gov for broader searches.
_POPULAR_SERIES: list[dict[str, str]] = [
    {
        "id": "CUUR0000SA0",
        "title": "Consumer Price Index - All Urban Consumers (CPI-U)",
        "description": "Monthly CPI for all items in U.S. city average, "
        "not seasonally adjusted. Measures changes in prices paid by consumers.",
        "keywords": "cpi consumer price index inflation cost living prices urban",
    },
    {
        "id": "LNS14000000",
        "title": "Unemployment Rate (Seasonally Adjusted)",
        "description": "Monthly national unemployment rate from the Current Population Survey.",
        "keywords": "unemployment rate jobs labor jobless",
    },
    {
        "id": "CES0000000001",
        "title": "Total Nonfarm Employment (Seasonally Adjusted)",
        "description": "Monthly total nonfarm payroll employment, seasonally adjusted.",
        "keywords": "employment nonfarm payroll jobs workers hired",
    },
    {
        "id": "LNS11000000",
        "title": "Civilian Labor Force Level",
        "description": "Monthly civilian labor force level (thousands), seasonally adjusted.",
        "keywords": "labor force workers civilian participation workforce",
    },
    {
        "id": "CUUR0000SAF1",
        "title": "Consumer Price Index - Food",
        "description": "CPI for food, all urban consumers, not seasonally adjusted.",
        "keywords": "food prices cpi grocery cost",
    },
    {
        "id": "CUUR0000SETB01",
        "title": "Consumer Price Index - Gasoline",
        "description": "CPI for gasoline (all types), all urban consumers.",
        "keywords": "gas gasoline fuel energy prices oil",
    },
    {
        "id": "CUUR0000SAH1",
        "title": "Consumer Price Index - Shelter",
        "description": "CPI for shelter costs, all urban consumers.",
        "keywords": "housing shelter rent prices cpi home",
    },
    {
        "id": "CUUR0000SAM",
        "title": "Consumer Price Index - Medical Care",
        "description": "CPI for medical care, all urban consumers.",
        "keywords": "medical health care prices cpi hospital doctor",
    },
    {
        "id": "OEUN000000005",
        "title": "Quarterly Census of Employment and Wages - Total All Industries",
        "description": "Quarterly employment and wages data for all industries nationwide.",
        "keywords": "wages salary employment earnings quarterly industries compensation",
    },
    {
        "id": "PRS85006092",
        "title": "Nonfarm Business Sector: Labor Productivity",
        "description": "Output per hour of all persons in the nonfarm business sector.",
        "keywords": "productivity labor output efficiency nonfarm business",
    },
]


class BLSSource:
    source_name: str = "bls"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search BLS popular series by keyword matching."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[int, dict]] = []
        for series in _POPULAR_SERIES:
            text = f"{series['keywords']} {series['title']} {series['description']}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, series))

        scored.sort(key=lambda x: x[0], reverse=True)

        api_key = settings.bls_api_key
        results: list[DatasetResult] = []
        for _hits, series in scored[:limit]:
            series_id = series["id"]
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=series_id,
                    title=series["title"],
                    description=series["description"],
                    formats=["JSON"],
                    download_url=self._build_download_url(series_id, api_key),
                    metadata={"series_id": series_id},
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return self._build_download_url(dataset_id, settings.bls_api_key)

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download BLS series data as JSON."""
        if not dataset_id:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{dataset_id}.json"

        body: dict = {"seriesid": [dataset_id], "startyear": "2014", "endyear": "2024"}
        api_key = settings.bls_api_key
        if api_key:
            body["registrationkey"] = api_key

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(BASE_URL, json=body)
                resp.raise_for_status()
                payload = resp.json()

            results = payload.get("Results", {}).get("series", [])
            if not results or not results[0].get("data"):
                logger.warning("BLS returned no data for %s", dataset_id)
                return None

            # Flatten to array of observation records
            records = []
            for obs in results[0]["data"]:
                records.append(
                    {
                        "year": obs.get("year"),
                        "period": obs.get("period"),
                        "period_name": obs.get("periodName"),
                        "value": obs.get("value"),
                    }
                )

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("BLS download failed for %s: %s", dataset_id, exc)
            return None

    @staticmethod
    def _build_download_url(series_id: str, api_key: str) -> str:
        """Build a BLS API download URL.

        Note: BLS API uses POST, so this URL is for reference.
        The actual download happens via the download() method.
        """
        return f"https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}"
