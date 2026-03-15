"""EIA (U.S. Energy Information Administration) API v2 adapter.

Uses the EIA Open Data API at api.eia.gov/v2 to search for and download
energy datasets. Requires a free API key from
https://www.eia.gov/opendata/register.php
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

BASE_URL = "https://api.eia.gov/v2"
TIMEOUT = 30.0
PAGE_SIZE = 5000

# Curated index of popular EIA datasets.
# The EIA API is hierarchical with no search endpoint, so we map common
# energy topics to their API route + data columns.
_POPULAR_DATASETS = [
    {
        "route": "electricity/retail-sales",
        "id": "electricity/retail-sales",
        "title": "Electricity Retail Sales",
        "description": (
            "Monthly and annual electricity retail sales, revenue,"
            " price, and customer counts by state and sector."
        ),
        "keywords": (
            "electricity retail sales revenue price customers"
            " state residential commercial industrial kwh"
        ),
        "data_cols": ["revenue", "sales", "price", "customers"],
    },
    {
        "route": "electricity/facility-fuel",
        "id": "electricity/facility-fuel",
        "title": "Electricity Generation by Fuel Type",
        "description": (
            "Monthly electricity generation, fuel consumption,"
            " and capacity by power plant and fuel type."
        ),
        "keywords": (
            "electricity generation fuel coal natural gas"
            " nuclear wind solar hydro power plant capacity"
        ),
        "data_cols": [
            "generation",
            "gross-generation",
            "consumption-for-eg",
        ],
    },
    {
        "route": (
            "electricity/state-electricity-profiles"
            "/emissions-by-state-by-fuel"
        ),
        "id": (
            "electricity/state-electricity-profiles"
            "/emissions-by-state-by-fuel"
        ),
        "title": "Power Sector CO2 Emissions by State and Fuel",
        "description": (
            "Annual CO2 emissions from the electric power sector"
            " by state and fuel type."
        ),
        "keywords": (
            "co2 emissions carbon dioxide electricity power"
            " sector state fuel coal gas petroleum climate"
        ),
        "data_cols": ["co2-thousand-metric-tons"],
    },
    {
        "route": "petroleum/pri/gnd",
        "id": "petroleum/pri/gnd",
        "title": "Weekly Retail Gasoline and Diesel Prices",
        "description": (
            "Weekly retail gasoline and diesel fuel prices"
            " by grade and region."
        ),
        "keywords": (
            "gasoline diesel fuel price retail weekly"
            " gas pump price oil petroleum"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "petroleum/crd/crpdn",
        "id": "petroleum/crd/crpdn",
        "title": "U.S. Crude Oil Production",
        "description": (
            "Monthly crude oil field production"
            " by state and PADD district."
        ),
        "keywords": (
            "crude oil production drilling wells"
            " barrels state monthly petroleum"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "petroleum/sum/sndw",
        "id": "petroleum/sum/sndw",
        "title": "Weekly Petroleum Supply and Disposition",
        "description": (
            "Weekly U.S. petroleum supply, disposition, and"
            " stocks including crude oil and gasoline."
        ),
        "keywords": (
            "petroleum supply stocks inventory crude oil"
            " gasoline distillate weekly imports exports"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "natural-gas/pri/sum",
        "id": "natural-gas/pri/sum",
        "title": "Natural Gas Prices",
        "description": (
            "Monthly and annual natural gas prices by type"
            " and state."
        ),
        "keywords": (
            "natural gas price residential commercial"
            " industrial wellhead citygate electric power"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "natural-gas/sum/lsum",
        "id": "natural-gas/sum/lsum",
        "title": "Natural Gas Supply and Disposition",
        "description": (
            "Monthly natural gas supply, disposition, and"
            " consumption by state and sector."
        ),
        "keywords": (
            "natural gas supply consumption production"
            " imports exports pipeline state monthly"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "coal/shipments",
        "id": "coal/shipments",
        "title": "Coal Shipments",
        "description": (
            "Quarterly coal shipments between mines and"
            " power plants, including tonnage and price."
        ),
        "keywords": (
            "coal shipments mine power plant tonnage"
            " price heat sulfur ash state quarterly"
        ),
        "data_cols": [
            "quantity",
            "price",
            "heat-content",
            "sulfur-content",
            "ash-content",
        ],
    },
    {
        "route": "total-energy/data",
        "id": "total-energy/data",
        "title": "Monthly Energy Review (Total Energy)",
        "description": (
            "Comprehensive monthly energy statistics across"
            " all sources: petroleum, gas, coal, nuclear,"
            " renewables."
        ),
        "keywords": (
            "total energy production consumption imports"
            " exports monthly petroleum gas coal nuclear"
            " renewables btu"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "seds/data",
        "id": "seds/data",
        "title": "State Energy Data System (SEDS)",
        "description": (
            "Annual state-level energy production,"
            " consumption, prices, and expenditures"
            " by source and sector from 1960 to present."
        ),
        "keywords": (
            "state energy production consumption price"
            " expenditure annual seds renewable fossil"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "steo/data",
        "id": "steo/data",
        "title": "Short-Term Energy Outlook (STEO)",
        "description": (
            "18-month energy market projections for"
            " petroleum, natural gas, coal, electricity,"
            " and renewables."
        ),
        "keywords": (
            "forecast outlook projection energy price"
            " production consumption short term steo"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "electricity/electric-power-operational-data",
        "id": "electricity/electric-power-operational-data",
        "title": "Electric Power Operational Data",
        "description": (
            "Monthly electricity generation, consumption,"
            " stocks, and cost of fossil fuels by state."
        ),
        "keywords": (
            "electric power operational generation"
            " consumption fuel cost receipts stocks"
            " state monthly"
        ),
        "data_cols": [
            "generation",
            "total-consumption",
            "cost-per-btu",
        ],
    },
    {
        "route": "international/data",
        "id": "international/data",
        "title": "International Energy Statistics",
        "description": (
            "Country-level energy data for 200+ countries:"
            " production, consumption, imports, exports,"
            " and reserves."
        ),
        "keywords": (
            "international country world global energy"
            " production consumption reserves petroleum"
            " gas coal electricity renewable"
        ),
        "data_cols": ["value"],
    },
    {
        "route": "crude-oil-imports/data",
        "id": "crude-oil-imports/data",
        "title": "U.S. Crude Oil Imports",
        "description": (
            "Monthly crude oil imports by country of origin,"
            " destination PADD district, and grade."
        ),
        "keywords": (
            "crude oil imports country origin destination"
            " grade barrels monthly opec"
        ),
        "data_cols": ["quantity"],
    },
    {
        "route": "nuclear-outages/facility-nuclear-outages",
        "id": "nuclear-outages/facility-nuclear-outages",
        "title": "Nuclear Power Plant Outages",
        "description": (
            "Daily nuclear power plant outage and capacity"
            " data by facility."
        ),
        "keywords": (
            "nuclear power plant outage capacity"
            " generation facility reactor"
        ),
        "data_cols": ["outage", "capacity"],
    },
]


class EIASource:
    source_name: str = "eia"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search curated EIA datasets by keyword matching."""
        api_key = settings.eia_api_key
        if not api_key:
            logger.debug("EIA API key not configured, skipping")
            return []

        keywords = extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[int, dict]] = []
        for ds in _POPULAR_DATASETS:
            text = f"{ds['keywords']} {ds['title']} {ds['description']}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ds))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ds in scored[:limit]:
            download_url = (
                f"{BASE_URL}/{ds['route']}"
                f"?api_key={api_key}&frequency=monthly&length={PAGE_SIZE}"
            )
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=ds["id"],
                    title=ds["title"],
                    description=ds["description"],
                    formats=["JSON"],
                    download_url=download_url,
                    metadata={"data_columns": ds.get("data_cols", [])},
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        api_key = settings.eia_api_key
        if not api_key or not dataset_id:
            return None
        return (
            f"{BASE_URL}/{dataset_id}"
            f"?api_key={api_key}&frequency=monthly&length={PAGE_SIZE}"
        )

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download EIA data as JSON with pagination."""
        api_key = settings.eia_api_key
        if not api_key:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_")
        dest = dest_dir / f"{safe_name}.json"

        all_records: list[dict] = []
        offset = 0

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                while True:
                    params: dict[str, str | int] = {
                        "api_key": api_key,
                        "length": PAGE_SIZE,
                        "offset": offset,
                    }
                    resp = await client.get(
                        f"{BASE_URL}/{dataset_id}", params=params
                    )
                    resp.raise_for_status()
                    payload = resp.json()

                    response_data = payload.get("response", {})
                    records = response_data.get("data", [])
                    if not records:
                        break

                    all_records.extend(records)
                    total = int(response_data.get("total", 0))

                    offset += len(records)
                    if offset >= total:
                        break

                    # Safety cap: 50k rows max
                    if len(all_records) >= 50000:
                        logger.info(
                            "EIA download capped at %d rows for %s",
                            len(all_records),
                            dataset_id,
                        )
                        break

            if not all_records:
                logger.warning("EIA returned no data for %s", dataset_id)
                return None

            dest.write_text(json.dumps(all_records, ensure_ascii=False))
            return dest
        except (httpx.HTTPError, OSError, ValueError) as exc:
            logger.warning("EIA download failed for %s: %s", dataset_id, exc)
            return None
