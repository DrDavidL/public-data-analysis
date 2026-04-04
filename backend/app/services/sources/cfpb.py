"""CFPB Consumer Complaint Database adapter.

Uses the Consumer Financial Protection Bureau complaints API at
consumerfinance.gov. No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1"
_client = SourceHTTPClient("cfpb", timeout=30.0)


class CFPBSource:
    source_name: str = "cfpb"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search CFPB consumer complaints matching *query*."""
        params = {
            "search_term": query,
            "size": min(limit, 10),
            "sort": "relevance_desc",
            "no_aggs": "true",
        }
        try:
            data = await _client.get_json(f"{BASE_URL}/", params=params)
        except Exception as exc:
            logger.warning("CFPB search failed for query=%r: %s", query, exc)
            return []

        total = data.get("hits", {}).get("total", {}).get("value", 0)

        # Return a single aggregated result pointing to the full query
        if total == 0:
            return []

        # Build a representative result
        hits = data.get("hits", {}).get("hits", [])
        products: set[str] = set()
        companies: set[str] = set()
        for hit in hits[:20]:
            src = hit.get("_source", {})
            if p := src.get("product"):
                products.add(p)
            if c := src.get("company"):
                companies.add(c)

        desc_parts = [f"{total:,} complaints found"]
        if products:
            desc_parts.append(f"Products: {', '.join(sorted(products)[:5])}")
        if companies:
            desc_parts.append(f"Companies: {', '.join(sorted(companies)[:5])}")

        results = [
            DatasetResult(
                source=self.source_name,
                id=f"complaints:{query}",
                title=f"CFPB Consumer Complaints — {query}",
                description="; ".join(desc_parts)[:500],
                formats=["JSON"],
                download_url=f"{BASE_URL}/?search_term={query}&size=10000&no_aggs=true",
                metadata={"total_complaints": total},
            )
        ]
        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        term = dataset_id.split(":", 1)[-1] if ":" in dataset_id else dataset_id
        return f"{BASE_URL}/?search_term={term}&size=10000&no_aggs=true"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download CFPB complaints as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        term = dataset_id.split(":", 1)[-1] if ":" in dataset_id else dataset_id
        safe_name = term.replace("/", "_").replace(" ", "_")[:80]
        dest = dest_dir / f"cfpb_{safe_name}.json"

        params = {
            "search_term": term,
            "size": 10000,
            "no_aggs": "true",
        }
        try:
            data = await _client.get_json(f"{BASE_URL}/", params=params, use_cache=False)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                logger.warning("CFPB returned no complaints for %s", dataset_id)
                return None

            records = []
            for hit in hits:
                src = hit.get("_source", {})
                records.append(
                    {
                        "complaint_id": src.get("complaint_id"),
                        "date_received": src.get("date_received"),
                        "product": src.get("product"),
                        "sub_product": src.get("sub_product"),
                        "issue": src.get("issue"),
                        "sub_issue": src.get("sub_issue"),
                        "company": src.get("company"),
                        "state": src.get("state"),
                        "zip_code": src.get("zip_code"),
                        "company_response": src.get("company_response"),
                        "timely_response": src.get("timely"),
                        "consumer_disputed": src.get("consumer_disputed"),
                        "complaint_narrative": src.get("complaint_what_happened"),
                    }
                )

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("CFPB download failed for %s: %s", dataset_id, exc)
            return None
