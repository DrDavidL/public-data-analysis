"""SEC EDGAR (Electronic Data Gathering, Analysis, and Retrieval) adapter.

Uses the SEC EDGAR full-text search API at efts.sec.gov to search company
filings (10-K, 10-Q, 8-K, etc.). No API key required — only a User-Agent
header identifying the caller.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient

logger = logging.getLogger(__name__)

SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
FULLTEXT_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar"
FILINGS_URL = "https://data.sec.gov/submissions"

_client = SourceHTTPClient(
    "sec_edgar",
    timeout=30.0,
    headers={"User-Agent": "PublicDataAnalysis/1.0 (research@example.com)"},
)


class SECEdgarSource:
    source_name: str = "sec_edgar"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search SEC EDGAR full-text search API."""
        params = {
            "q": query,
            "dateRange": "custom",
            "startdt": "2020-01-01",
            "enddt": "2026-12-31",
            "forms": "10-K,10-Q,8-K",
        }
        try:
            data = await _client.get_json("https://efts.sec.gov/LATEST/search-index", params=params)
        except Exception:
            # Fallback: use the main EDGAR full-text search
            try:
                data = await _client.get_json(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={"q": query, "forms": "10-K,10-Q,8-K"},
                )
            except Exception as exc:
                logger.warning("SEC EDGAR search failed for query=%r: %s", query, exc)
                return []

        results: list[DatasetResult] = []
        hits = data.get("hits", {}).get("hits", data.get("hits", []))
        if isinstance(hits, dict):
            hits = hits.get("hits", [])

        for hit in hits[:limit]:
            src = hit.get("_source", hit)
            file_num = src.get("file_num", "")
            display_names = src.get("display_names", [])
            entity = src.get("entity_name", display_names[0] if display_names else "")
            form_type = src.get("form_type", src.get("file_type", ""))
            filed = src.get("file_date", src.get("period_of_report", ""))
            filing_url = src.get("file_url", "")

            filing_id = src.get("accession_no", file_num or str(hash(str(src)))[:12])
            title = f"{entity} — {form_type}" if entity else form_type

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=filing_id,
                    title=title[:200],
                    description=f"SEC filing {form_type} by {entity}. Filed: {filed}"[:500],
                    formats=["JSON"],
                    download_url=filing_url or None,
                    metadata={
                        k: v
                        for k, v in {
                            "form_type": form_type,
                            "entity": entity,
                            "filed": filed,
                        }.items()
                        if v
                    },
                )
            )

        # If EFTS returned nothing, try company tickers search as fallback
        if not results:
            return await self._search_company_tickers(query, limit)

        return results

    async def _search_company_tickers(self, query: str, limit: int) -> list[DatasetResult]:
        """Fallback: search SEC company tickers JSON."""
        try:
            tickers = await _client.get_json("https://www.sec.gov/files/company_tickers.json")
        except Exception:
            return []

        query_lower = query.lower()
        results: list[DatasetResult] = []
        for _key, entry in tickers.items():
            name = entry.get("title", "")
            ticker = entry.get("ticker", "")
            cik = str(entry.get("cik_str", ""))
            if query_lower in name.lower() or query_lower in ticker.lower():
                cik_padded = cik.zfill(10)
                results.append(
                    DatasetResult(
                        source=self.source_name,
                        id=f"CIK{cik_padded}",
                        title=f"{name} ({ticker})",
                        description=f"SEC filings for {name} (CIK: {cik})",
                        formats=["JSON"],
                        download_url=f"{FILINGS_URL}/CIK{cik_padded}.json",
                        metadata={"ticker": ticker, "cik": cik},
                    )
                )
                if len(results) >= limit:
                    break

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not dataset_id:
            return None
        if dataset_id.startswith("CIK"):
            return f"{FILINGS_URL}/{dataset_id}.json"
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download SEC filing data as JSON."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = dataset_id.replace("/", "_").replace("\\", "_")[:80]
        dest = dest_dir / f"sec_{safe_name}.json"

        if dataset_id.startswith("CIK"):
            url = f"{FILINGS_URL}/{dataset_id}.json"
            try:
                data = await _client.get_json(url, use_cache=False)

                # Flatten recent filings into tabular records
                recent = data.get("filings", {}).get("recent", {})
                if not recent:
                    logger.warning("SEC EDGAR returned no recent filings for %s", dataset_id)
                    return None

                forms = recent.get("form", [])
                dates = recent.get("filingDate", [])
                accessions = recent.get("accessionNumber", [])
                primary_docs = recent.get("primaryDocument", [])
                descriptions = recent.get("primaryDocDescription", [])

                records = []
                for i in range(len(forms)):
                    records.append(
                        {
                            "form_type": forms[i] if i < len(forms) else "",
                            "filing_date": dates[i] if i < len(dates) else "",
                            "accession_number": (accessions[i] if i < len(accessions) else ""),
                            "primary_document": (primary_docs[i] if i < len(primary_docs) else ""),
                            "description": (descriptions[i] if i < len(descriptions) else ""),
                        }
                    )

                dest.write_text(json.dumps(records, ensure_ascii=False))
                return dest
            except Exception as exc:
                logger.warning("SEC EDGAR download failed for %s: %s", dataset_id, exc)
                return None

        return None
