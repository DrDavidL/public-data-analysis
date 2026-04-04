"""FDIC BankFind API adapter.

Uses the FDIC BankFind Suite API at banks.data.fdic.gov to search
bank financial data (quarterly reports). No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://banks.data.fdic.gov/api"
_client = SourceHTTPClient("fdic", timeout=30.0)

# Curated FDIC financial report fields
_FINANCIAL_FIELDS = (
    "REPDTE,CERT,INSTNAME,CITY,STNAME,ASSET,DEP,DEPDOM,"
    "NETINC,EINTEXP,ROA,ROE,NITEFDINM,LNLSNET,ELNANTR"
)

_DATASETS = [
    {
        "id": "fdic_financials",
        "title": "FDIC Bank Financial Reports",
        "description": (
            "Quarterly financial data for FDIC-insured institutions. "
            "Includes total assets, deposits, net income, return on assets, "
            "return on equity, loans, and other key banking metrics."
        ),
        "keywords": (
            "bank financial assets deposits net income roa roe loans "
            "fdic insured institution quarterly capital"
        ),
    },
    {
        "id": "fdic_institutions",
        "title": "FDIC Institution Directory",
        "description": (
            "Directory of FDIC-insured banking institutions with "
            "charter type, location, regulator, and active/inactive status."
        ),
        "keywords": (
            "bank institution directory charter location regulator fdic active inactive branch"
        ),
    },
]


class FDICSource:
    source_name: str = "fdic"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search FDIC data by keyword matching and live institution lookup."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        # Score curated datasets
        scored: list[tuple[int, dict]] = []
        for ds in _DATASETS:
            text = f"{ds['keywords']} {ds['title']} {ds['description']}".lower()
            hits = sum(1 for kw in keywords if kw in text)
            if hits > 0:
                scored.append((hits, ds))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _hits, ds in scored[:limit]:
            if ds["id"] == "fdic_financials":
                download_url = (
                    f"{BASE_URL}/financials?"
                    f"filters=REPDTE%3A20240331&"
                    f"fields={_FINANCIAL_FIELDS}&"
                    f"sort_by=ASSET&sort_order=DESC&limit=1000&offset=0"
                )
            else:
                download_url = (
                    f"{BASE_URL}/institutions?"
                    f"search={query}&fields=INSTNAME,CERT,CITY,STNAME,"
                    f"CHARTER_CLASS,ACTIVE&limit=1000&offset=0"
                )
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=ds["id"],
                    title=ds["title"],
                    description=ds["description"],
                    formats=["JSON"],
                    download_url=download_url,
                    metadata={},
                )
            )

        # Also try live institution search
        if len(results) < limit:
            try:
                params = {
                    "search": query,
                    "fields": "INSTNAME,CERT,CITY,STNAME,ASSET,DEP",
                    "limit": min(limit - len(results), 5),
                }
                data = await _client.get_json(f"{BASE_URL}/institutions", params=params)
                for inst in data.get("data", []):
                    props = inst.get("data", {})
                    cert = str(props.get("CERT", ""))
                    name = props.get("INSTNAME", "")
                    if not cert or not name:
                        continue
                    results.append(
                        DatasetResult(
                            source=self.source_name,
                            id=f"inst:{cert}",
                            title=f"{name} — FDIC Financial Data",
                            description=(
                                f"Financial reports for {name}, "
                                f"{props.get('CITY', '')}, {props.get('STNAME', '')}"
                            ),
                            formats=["JSON"],
                            download_url=(
                                f"{BASE_URL}/financials?"
                                f"filters=CERT%3A{cert}&"
                                f"fields={_FINANCIAL_FIELDS}&"
                                f"sort_by=REPDTE&sort_order=DESC&limit=100"
                            ),
                            metadata={
                                "cert": cert,
                                "total_assets": props.get("ASSET"),
                                "total_deposits": props.get("DEP"),
                            },
                        )
                    )
            except Exception:
                pass

        return results[:limit]

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        if dataset_id.startswith("inst:"):
            cert = dataset_id.split(":", 1)[1]
            return (
                f"{BASE_URL}/financials?"
                f"filters=CERT%3A{cert}&"
                f"fields={_FINANCIAL_FIELDS}&"
                f"sort_by=REPDTE&sort_order=DESC&limit=100"
            )
        if dataset_id == "fdic_financials":
            return (
                f"{BASE_URL}/financials?"
                f"fields={_FINANCIAL_FIELDS}&"
                f"sort_by=ASSET&sort_order=DESC&limit=1000&offset=0"
            )
        if dataset_id == "fdic_institutions":
            return (
                f"{BASE_URL}/institutions?"
                f"fields=INSTNAME,CERT,CITY,STNAME,CHARTER_CLASS,ACTIVE&"
                f"limit=1000&offset=0"
            )
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download FDIC data as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace(":", "_")[:80]
        dest = dest_dir / f"fdic_{safe_name}.json"

        url = await self.get_download_url(dataset_id)
        if not url:
            return None

        try:
            data = await _client.get_json(url, use_cache=False)
            entries = data.get("data", [])
            if not entries:
                logger.warning("FDIC returned no data for %s", dataset_id)
                return None

            records = [e.get("data", e) for e in entries]
            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("FDIC download failed for %s: %s", dataset_id, exc)
            return None
