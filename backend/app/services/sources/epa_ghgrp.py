"""EPA GHGRP (Greenhouse Gas Reporting Program) adapter.

Uses the EPA Envirofacts API at enviro.epa.gov to access facility-level
greenhouse gas emissions data. No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://enviro.epa.gov/enviro/efservice"
_client = SourceHTTPClient("epa_ghgrp", timeout=30.0)

# Key GHGRP tables available through Envirofacts
_DATASETS = [
    {
        "table": "PUB_DIM_FACILITY",
        "id": "ghgrp_facilities",
        "title": "EPA GHGRP — Facility Emissions",
        "description": (
            "Facility-level greenhouse gas emissions reported to the EPA. "
            "Includes facility name, location, parent company, industry type, "
            "and total reported emissions in metric tons CO2e."
        ),
        "keywords": (
            "greenhouse gas emissions facility ghg co2 carbon dioxide "
            "methane climate epa reporting industry plant"
        ),
    },
    {
        "table": "PUB_DIM_GHG",
        "id": "ghgrp_gases",
        "title": "EPA GHGRP — Gas-Level Emissions",
        "description": (
            "Per-gas emissions breakdown for reporting facilities. "
            "Includes CO2, CH4, N2O, and fluorinated gases with quantities."
        ),
        "keywords": (
            "greenhouse gas co2 methane ch4 n2o fluorinated hfc pfc sf6 emissions breakdown"
        ),
    },
    {
        "table": "PUB_DIM_SECTOR",
        "id": "ghgrp_sectors",
        "title": "EPA GHGRP — Emissions by Industry Sector",
        "description": (
            "Greenhouse gas emissions aggregated by industry sector. "
            "Covers power plants, petroleum, chemicals, minerals, metals, waste, "
            "and other industrial categories."
        ),
        "keywords": (
            "sector industry power plant petroleum refinery chemical "
            "cement steel waste landfill emissions"
        ),
    },
]


class EPAGHGRPSource:
    source_name: str = "epa_ghgrp"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search EPA GHGRP datasets by keyword matching."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[int, dict]] = []
        for ds in _DATASETS:
            text = f"{ds['keywords']} {ds['title']} {ds['description']}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ds))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ds in scored[:limit]:
            download_url = f"{BASE_URL}/{ds['table']}/rows/0:1000/JSON"
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=ds["id"],
                    title=ds["title"],
                    description=ds["description"],
                    formats=["JSON"],
                    download_url=download_url,
                    metadata={"table": ds["table"]},
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        for ds in _DATASETS:
            if ds["id"] == dataset_id:
                return f"{BASE_URL}/{ds['table']}/rows/0:5000/JSON"
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download EPA GHGRP data as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_")[:80]
        dest = dest_dir / f"epa_{safe_name}.json"

        table = None
        for ds in _DATASETS:
            if ds["id"] == dataset_id:
                table = ds["table"]
                break

        if not table:
            logger.warning("Unknown EPA GHGRP dataset: %s", dataset_id)
            return None

        all_records: list = []
        offset = 0
        page_size = 1000

        try:
            while True:
                url = f"{BASE_URL}/{table}/rows/{offset}:{offset + page_size}/JSON"
                data = await _client.get_json(url, use_cache=False)

                if not isinstance(data, list) or not data:
                    break

                all_records.extend(data)
                offset += page_size

                # Safety cap
                if len(all_records) >= 10000:
                    logger.info(
                        "EPA GHGRP download capped at %d rows for %s",
                        len(all_records),
                        dataset_id,
                    )
                    break

                if len(data) < page_size:
                    break

            if not all_records:
                logger.warning("EPA GHGRP returned no data for %s", dataset_id)
                return None

            dest.write_text(json.dumps(all_records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("EPA GHGRP download failed for %s: %s", dataset_id, exc)
            return None
