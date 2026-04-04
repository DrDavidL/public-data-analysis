"""OpenFDA API adapter.

Uses the openFDA API at api.fda.gov for drug adverse events and
enforcement/recall actions. No authentication required (optional API key
increases rate limits).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fda.gov"
_client = SourceHTTPClient("openfda", timeout=30.0)

# Searchable OpenFDA endpoints
_ENDPOINTS = [
    {
        "path": "/drug/event.json",
        "id_prefix": "drug_event",
        "title": "Drug Adverse Events (FAERS)",
        "description": (
            "FDA Adverse Event Reporting System data on side effects "
            "and medication errors for drugs and therapeutic biologics."
        ),
        "keywords": "drug adverse event side effect medication error reaction safety faers",
        "search_field": "patient.drug.openfda.brand_name",
    },
    {
        "path": "/drug/enforcement.json",
        "id_prefix": "drug_enforcement",
        "title": "Drug Recalls & Enforcement",
        "description": (
            "FDA enforcement reports including drug recalls, market withdrawals, and safety alerts."
        ),
        "keywords": "drug recall enforcement withdrawal safety alert fda market",
        "search_field": "reason_for_recall",
    },
    {
        "path": "/device/event.json",
        "id_prefix": "device_event",
        "title": "Medical Device Adverse Events",
        "description": (
            "Reports of adverse events involving medical devices, "
            "including malfunctions and patient injuries."
        ),
        "keywords": "device adverse event malfunction injury medical implant",
        "search_field": "device.generic_name",
    },
    {
        "path": "/food/enforcement.json",
        "id_prefix": "food_enforcement",
        "title": "Food Recalls & Enforcement",
        "description": (
            "FDA enforcement reports for food products including recalls "
            "for contamination, allergens, and mislabeling."
        ),
        "keywords": "food recall contamination allergen safety enforcement fda",
        "search_field": "reason_for_recall",
    },
]


class OpenFDASource:
    source_name: str = "openfda"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search OpenFDA endpoints by keyword matching and live API queries."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        # Score endpoints by keyword relevance
        scored: list[tuple[int, dict]] = []
        for ep in _ENDPOINTS:
            text = f"{ep['keywords']} {ep['title']} {ep['description']}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ep))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ep in scored[:limit]:
            # Try a live count query to show result size
            search_term = "+AND+".join(keywords[:3])
            api_url = f"{BASE_URL}{ep['path']}?search={search_term}&limit=1"

            meta: dict = {}
            try:
                data = await _client.get_json(api_url)
                total = data.get("meta", {}).get("results", {}).get("total", 0)
                meta["total_results"] = total
            except Exception:
                pass

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=f"{ep['id_prefix']}:{'+'.join(keywords[:3])}",
                    title=f"{ep['title']} — {query}",
                    description=ep["description"],
                    formats=["JSON"],
                    download_url=f"{BASE_URL}{ep['path']}?search={search_term}&limit=1000",
                    metadata=meta,
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        parts = dataset_id.split(":", 1)
        if len(parts) != 2:
            return None
        prefix, terms = parts
        for ep in _ENDPOINTS:
            if ep["id_prefix"] == prefix:
                return f"{BASE_URL}{ep['path']}?search={terms}&limit=1000"
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download OpenFDA data as JSON."""
        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace(":", "_").replace("+", "_")[:80]
        dest = dest_dir / f"openfda_{safe_name}.json"

        try:
            data = await _client.get_json(url, use_cache=False)
            records = data.get("results", [])
            if not records:
                logger.warning("OpenFDA returned no data for %s", dataset_id)
                return None

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("OpenFDA download failed for %s: %s", dataset_id, exc)
            return None
