"""OECD SDMX REST API adapter.

Searches the OECD dataflow catalog and downloads data as CSV via the
SDMX API at sdmx.oecd.org. No API key required.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords as _extract_keywords

logger = logging.getLogger(__name__)

DATAFLOW_URL = "https://sdmx.oecd.org/public/rest/dataflow/all"
DATA_URL = "https://sdmx.oecd.org/public/rest/data"
TIMEOUT = 20.0


class OECDSource:
    source_name: str = "oecd"

    # Class-level dataflow cache (refreshed every 24 hours)
    _dataflows_cache: list[dict] = []
    _dataflows_timestamp: float = 0.0
    CACHE_TTL = 86400

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search OECD dataflows matching *query* keywords."""
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            dataflows = await self._get_dataflows(client)

        keywords = _extract_keywords(query)
        if not keywords:
            return []

        # Score dataflows by keyword matches in name
        min_hits = max(1, len(keywords) // 2)
        scored: list[tuple[int, dict]] = []
        for df in dataflows:
            name_lower = df.get("name", "").lower()
            hits = sum(1 for kw in keywords if kw in name_lower)
            if hits >= min_hits:
                scored.append((hits, df))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, df in scored[:limit]:
            df_id = df["id"]
            agency = df["agency"]
            version = df["version"]
            name = df["name"]

            # Build data URL: all dimensions wildcard, CSV format
            download_url = f"{DATA_URL}/{agency},{df_id},{version}/all"

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=f"{agency},{df_id},{version}",
                    title=name,
                    description=f"OECD dataset: {name}",
                    formats=["CSV"],
                    download_url=download_url,
                    metadata={
                        k: v
                        for k, v in {
                            "agency": agency,
                            "dataflow_id": df_id,
                            "version": version,
                        }.items()
                        if v
                    },
                )
            )

        return results

    @classmethod
    async def _get_dataflows(cls, client: httpx.AsyncClient) -> list[dict]:
        """Return all OECD dataflows, using a 24-hour in-memory cache."""
        now = time.monotonic()
        if cls._dataflows_cache and (now - cls._dataflows_timestamp) < cls.CACHE_TTL:
            return cls._dataflows_cache

        headers = {"Accept": "application/vnd.sdmx.structure+json"}
        try:
            resp = await client.get(DATAFLOW_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            logger.exception("OECD dataflow fetch failed, using stale cache")
            return cls._dataflows_cache

        dataflows: list[dict] = []
        for df in data.get("data", {}).get("dataflows", []):
            df_id = df.get("id", "")
            agency = df.get("agencyID", "")
            version = df.get("version", "")
            # name is a localized dict — prefer English
            name_dict = df.get("name") or {}
            if isinstance(name_dict, str):
                name = name_dict
            else:
                name = name_dict.get("en", name_dict.get("fr", str(name_dict)))

            if df_id and name:
                dataflows.append(
                    {
                        "id": df_id,
                        "agency": agency,
                        "version": version,
                        "name": name,
                    }
                )

        if dataflows:
            cls._dataflows_cache = dataflows
            cls._dataflows_timestamp = now
            logger.info("OECD dataflows cache refreshed (%d entries)", len(dataflows))

        return dataflows

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return f"{DATA_URL}/{dataset_id}/all"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download OECD data as CSV.

        The dataset_id format is ``agencyID,dataflowID,version``.
        We request CSV with ``startPeriod`` limited to avoid huge downloads.
        """
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace(",", "_").replace("/", "_")
        dest = dest_dir / f"{safe_name}.csv"

        headers = {"Accept": "text/csv"}
        # Limit to recent 10 years to keep downloads manageable
        params: dict[str, str] = {"startPeriod": "2014", "dimensionAtObservation": "AllDimensions"}

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()

            dest.write_bytes(resp.content)
            return dest
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("OECD download failed for %s: %s", dataset_id, exc)
            return None
