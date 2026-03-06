"""Census.gov API adapter.

Uses curated ACS 5-Year (2022) datasets with pre-built Census API query URLs
that return real tabular data at the county level.  No API key required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

TIMEOUT = 30.0

# ACS 5-Year 2022 base paths
_SUBJECT = "https://api.census.gov/data/2022/acs/acs5/subject"
_PROFILE = "https://api.census.gov/data/2022/acs/acs5/profile"

_POPULAR_DATASETS: list[dict[str, str]] = [
    {
        "id": "acs5_2022_health_insurance",
        "title": "Health Insurance Coverage by County (ACS 2022)",
        "description": (
            "Civilian noninstitutionalized population health insurance "
            "coverage. Includes total population, uninsured count, and "
            "uninsured percentage for every U.S. county."
        ),
        "keywords": (
            "health insurance uninsured coverage medical healthcare insured aca affordable care"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,S2701_C01_001E,S2701_C04_001E,S2701_C05_001E&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_population_demographics",
        "title": "Population & Demographics by County (ACS 2022)",
        "description": (
            "Total population, sex, median age, and race/ethnicity breakdown for every U.S. county."
        ),
        "keywords": (
            "population demographics race ethnicity age sex gender "
            "hispanic white black asian diversity census"
        ),
        "api_url": (
            f"{_PROFILE}?get=NAME,"
            "DP05_0001E,DP05_0002E,DP05_0003E,DP05_0018E,"
            "DP05_0071E,DP05_0077E,DP05_0078E,DP05_0080E"
            "&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_income",
        "title": "Household Income by County (ACS 2022)",
        "description": ("Median and mean household income for every U.S. county."),
        "keywords": ("income household median mean earnings salary wages money wealth economic"),
        "api_url": (f"{_SUBJECT}?get=NAME,S1901_C01_012E,S1901_C01_013E&for=county:*"),
    },
    {
        "id": "acs5_2022_poverty",
        "title": "Poverty Status by County (ACS 2022)",
        "description": (
            "Population below poverty level, count and percentage, for every U.S. county."
        ),
        "keywords": ("poverty poor low income below poverty level disadvantaged economic hardship"),
        "api_url": (
            f"{_SUBJECT}?get=NAME,S1701_C01_001E,S1701_C02_001E,S1701_C03_001E&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_employment",
        "title": "Employment & Labor Force by County (ACS 2022)",
        "description": (
            "Labor force participation rate, employment-population ratio, "
            "and unemployment rate for every U.S. county."
        ),
        "keywords": (
            "employment unemployment labor force jobs workers workforce participation jobless"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,"
            "S2301_C01_001E,S2301_C02_001E,S2301_C03_001E,S2301_C04_001E"
            "&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_education",
        "title": "Educational Attainment by County (ACS 2022)",
        "description": (
            "Percentage of population with high school diploma or higher, "
            "bachelor's degree or higher, and graduate degree."
        ),
        "keywords": (
            "education college degree bachelor highschool graduate school "
            "attainment diploma university"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,S1501_C02_014E,S1501_C02_015E,S1501_C02_013E&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_housing",
        "title": "Housing Characteristics by County (ACS 2022)",
        "description": (
            "Total housing units, occupied units, median gross rent, "
            "and median home value for every U.S. county."
        ),
        "keywords": (
            "housing rent home value property occupied units median rental homeowner shelter"
        ),
        "api_url": (
            f"{_PROFILE}?get=NAME,DP04_0001E,DP04_0002E,DP04_0134E,DP04_0089E&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_commuting",
        "title": "Commuting Patterns by County (ACS 2022)",
        "description": (
            "Workers 16+, drove alone percentage, public transit "
            "percentage, and work-from-home percentage."
        ),
        "keywords": (
            "commuting commute transportation transit drive work from "
            "home remote telecommute travel car bus"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,"
            "S0801_C01_001E,S0801_C01_003E,S0801_C01_009E,S0801_C01_013E"
            "&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_age",
        "title": "Age Distribution & Dependency by County (ACS 2022)",
        "description": (
            "Median age, percentage under 18, and percentage 65 and older for every U.S. county."
        ),
        "keywords": (
            "age median elderly senior youth children dependency aging old young retirement"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,S0101_C01_032E,S0101_C02_022E,S0101_C02_030E&for=county:*"
        ),
    },
    {
        "id": "acs5_2022_language",
        "title": "Language Spoken at Home by County (ACS 2022)",
        "description": (
            "English-only speakers, Spanish speakers, and limited "
            "English proficiency for every U.S. county."
        ),
        "keywords": (
            "language english spanish spoken home bilingual limited proficiency esl foreign"
        ),
        "api_url": (
            f"{_SUBJECT}?get=NAME,S1601_C01_002E,S1601_C01_003E,S1601_C01_010E&for=county:*"
        ),
    },
]


class CensusSource:
    source_name: str = "census"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search curated Census datasets by keyword matching."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        scored: list[tuple[int, dict]] = []
        for ds in _POPULAR_DATASETS:
            text = (f"{ds['keywords']} {ds['title']} {ds['description']}").lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ds))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ds in scored[:limit]:
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=ds["id"],
                    title=ds["title"],
                    description=ds["description"],
                    formats=["JSON"],
                    download_url=ds["api_url"],
                    metadata={"vintage": "2022", "geography": "county"},
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Look up the API URL for a curated dataset."""
        if not dataset_id:
            return None
        if dataset_id.startswith("http"):
            return dataset_id
        for ds in _POPULAR_DATASETS:
            if ds["id"] == dataset_id:
                return ds["api_url"]
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download Census data as JSON."""
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("?", "_").replace("&", "_")[:100]
        dest = dest_dir / f"census_{safe_name}.json"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                params: dict[str, str] = {}
                if "?" not in url:
                    params = {"get": "NAME", "for": "county:*"}

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
