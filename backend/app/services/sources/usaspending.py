"""USASpending.gov API adapter.

Uses the USASpending API at api.usaspending.gov to search for and download
federal award (contract/grant) data. No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://api.usaspending.gov/api/v2"
_client = SourceHTTPClient("usaspending", timeout=30.0)


class USASpendingSource:
    source_name: str = "usaspending"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search USASpending for federal award data matching *query*."""
        # USASpending API wants individual keyword strings, not one long phrase
        keywords = extract_keywords(query)
        if not keywords:
            return []
        body = {
            "filters": {"keywords": keywords[:5]},
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Awarding Agency",
                "Description",
                "Start Date",
                "End Date",
                "Award Type",
            ],
            "limit": min(limit, 25),
            "page": 1,
            "sort": "Award Amount",
            "order": "desc",
        }
        try:
            data = await _client.post_json(f"{BASE_URL}/search/spending_by_award/", json_body=body)
        except Exception as exc:
            logger.warning("USASpending search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for rec in data.get("results", [])[:limit]:
            award_id = rec.get("Award ID") or rec.get("internal_id", "")
            if not award_id:
                continue
            title = f"{rec.get('Recipient Name', 'Unknown')} — {rec.get('Award Type', 'Award')}"
            desc = rec.get("Description", "") or ""
            amount = rec.get("Award Amount")
            agency = rec.get("Awarding Agency", "")

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=str(award_id),
                    title=title[:200],
                    description=desc[:500],
                    formats=["JSON"],
                    download_url=f"{BASE_URL}/search/spending_by_award/",
                    metadata={
                        k: v
                        for k, v in {
                            "award_amount": amount,
                            "awarding_agency": agency,
                            "start_date": rec.get("Start Date"),
                            "end_date": rec.get("End Date"),
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return f"{BASE_URL}/search/spending_by_award/"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download USASpending award data as JSON.

        Uses keyword search to retrieve awards matching the dataset_id,
        which represents the original search keyword/award-id.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:80]
        dest = dest_dir / f"usaspending_{safe_name}.json"

        body = {
            "filters": {"keywords": [dataset_id]},
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Description",
                "Start Date",
                "End Date",
                "Award Type",
                "recipient_id",
                "Funding Agency",
                "Funding Sub Agency",
            ],
            "limit": 100,
            "page": 1,
            "sort": "Award Amount",
            "order": "desc",
        }
        try:
            data = await _client.post_json(f"{BASE_URL}/search/spending_by_award/", json_body=body)
            records = data.get("results", [])
            if not records:
                logger.warning("USASpending returned no data for %s", dataset_id)
                return None

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("USASpending download failed for %s: %s", dataset_id, exc)
            return None
