"""Federal Register API adapter.

Uses the Federal Register API at federalregister.gov to search for
executive orders, agency rules, proposed rules, and notices.
No authentication required.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient

logger = logging.getLogger(__name__)

BASE_URL = "https://www.federalregister.gov/api/v1"
_client = SourceHTTPClient("federal_register", timeout=30.0)


class FederalRegisterSource:
    source_name: str = "federal_register"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search Federal Register documents matching *query*."""
        params = {
            "conditions[term]": query,
            "per_page": min(limit, 20),
            "order": "relevance",
            "fields[]": [
                "title",
                "abstract",
                "document_number",
                "type",
                "agencies",
                "publication_date",
                "html_url",
                "pdf_url",
            ],
        }
        try:
            data = await _client.get_json(f"{BASE_URL}/documents.json", params=params)
        except Exception as exc:
            logger.warning("Federal Register search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for doc in data.get("results", [])[:limit]:
            doc_number = doc.get("document_number", "")
            if not doc_number:
                continue

            title = doc.get("title", "")
            abstract = doc.get("abstract", "") or ""
            doc_type = doc.get("type", "")
            pub_date = doc.get("publication_date", "")
            agencies = [a.get("name", "") for a in (doc.get("agencies") or []) if a.get("name")]

            desc_parts = []
            if doc_type:
                desc_parts.append(f"Type: {doc_type}")
            if agencies:
                desc_parts.append(f"Agencies: {', '.join(agencies[:3])}")
            if abstract:
                desc_parts.append(abstract[:300])

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=doc_number,
                    title=title[:200],
                    description="; ".join(desc_parts)[:500],
                    formats=["JSON"],
                    download_url=f"{BASE_URL}/documents.json?conditions[term]={query}&per_page=100",
                    metadata={
                        k: v
                        for k, v in {
                            "type": doc_type,
                            "publication_date": pub_date,
                            "agencies": ", ".join(agencies) if agencies else None,
                        }.items()
                        if v
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        return f"{BASE_URL}/documents/{dataset_id}.json"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download Federal Register documents as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:80]
        dest = dest_dir / f"fedreg_{safe_name}.json"

        # If dataset_id looks like a document number, fetch that single doc
        # Otherwise treat it as a search term and fetch a batch
        if "-" in dataset_id and len(dataset_id) < 30:
            # Single document
            try:
                data = await _client.get_json(
                    f"{BASE_URL}/documents/{dataset_id}.json", use_cache=False
                )
                dest.write_text(json.dumps([data], ensure_ascii=False))
                return dest
            except Exception:
                pass

        # Batch search
        params = {
            "conditions[term]": dataset_id,
            "per_page": 100,
            "order": "relevance",
        }
        try:
            data = await _client.get_json(
                f"{BASE_URL}/documents.json", params=params, use_cache=False
            )
            docs = data.get("results", [])
            if not docs:
                logger.warning("Federal Register returned no data for %s", dataset_id)
                return None

            records = []
            for doc in docs:
                records.append(
                    {
                        "document_number": doc.get("document_number", ""),
                        "title": doc.get("title", ""),
                        "type": doc.get("type", ""),
                        "abstract": doc.get("abstract", ""),
                        "publication_date": doc.get("publication_date", ""),
                        "agencies": ", ".join(
                            a.get("name", "") for a in (doc.get("agencies") or []) if a.get("name")
                        ),
                        "html_url": doc.get("html_url", ""),
                        "pdf_url": doc.get("pdf_url", ""),
                    }
                )

            dest.write_text(json.dumps(records, ensure_ascii=False))
            return dest
        except Exception as exc:
            logger.warning("Federal Register download failed for %s: %s", dataset_id, exc)
            return None
