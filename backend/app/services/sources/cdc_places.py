"""CDC PLACES adapter — local health estimates via Socrata SODA API.

Uses data.cdc.gov to search and download county-, place-, census-tract-,
and ZCTA-level health data (39 measures covering chronic disease,
prevention, risk behaviors, disability, and social needs).
No API key required (unauthenticated: 1 000 req/hr).
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.schemas.datasets import DatasetResult
from app.services.http_client import SourceHTTPClient

logger = logging.getLogger(__name__)

BASE = "https://data.cdc.gov/resource"

# 2025-release Socrata dataset IDs by geographic level
_DATASETS: dict[str, tuple[str, str]] = {
    "county": ("swc5-untb", "County"),
    "place": ("eav7-hnsx", "Place (City)"),
    "tract": ("cwsq-ngmh", "Census Tract"),
    "zcta": ("qnzd-25i4", "ZCTA (ZIP Code)"),
}

_client = SourceHTTPClient("cdc_places", timeout=30.0)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _fetch_measures() -> list[dict]:
    """Return the distinct measure list from the county dataset."""
    params = {
        "$select": "measureid,short_question_text,measure,category",
        "$group": "measureid,short_question_text,measure,category",
        "$order": "category,short_question_text",
        "$limit": "100",
    }
    return await _client.get_json(f"{BASE}/swc5-untb.json", params=params)


def _match_measures(measures: list[dict], query: str) -> list[dict]:
    """Keyword-match query against measure names/categories."""
    tokens = query.lower().split()
    scored: list[tuple[int, dict]] = []
    for m in measures:
        blob = " ".join(
            [
                m.get("short_question_text", ""),
                m.get("measure", ""),
                m.get("category", ""),
            ]
        ).lower()
        hits = sum(1 for t in tokens if t in blob)
        if hits:
            scored.append((hits, m))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored]


# ------------------------------------------------------------------
# Source class
# ------------------------------------------------------------------


class CDCPlacesSource:
    source_name: str = "cdc_places"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search CDC PLACES measures matching *query*.

        Returns up to *limit* results, one per (measure x geo-level) combo,
        prioritising county-level data.
        """
        try:
            measures = await _fetch_measures()
        except Exception as exc:
            logger.warning("CDC PLACES measure fetch failed: %s", exc)
            return []

        matched = _match_measures(measures, query)
        if not matched:
            # Fall back to Socrata full-text search
            try:
                rows = await _client.get_json(
                    f"{BASE}/swc5-untb.json",
                    params={"$q": query, "$limit": "5"},
                )
                # Deduplicate by measureid
                seen: set[str] = set()
                for r in rows:
                    mid = r.get("measureid", "")
                    if mid and mid not in seen:
                        seen.add(mid)
                        matched.append(r)
            except Exception:
                pass
        if not matched:
            return []

        results: list[DatasetResult] = []
        for m in matched:
            mid = m.get("measureid", "")
            short = m.get("short_question_text", mid)
            full = m.get("measure", short)
            cat = m.get("category", "")

            for geo_key, (dataset_id, geo_label) in _DATASETS.items():
                if len(results) >= limit:
                    break
                did = f"{geo_key}:{mid}"
                csv_url = (
                    f"{BASE}/{dataset_id}.csv"
                    f"?$where=measureid='{mid}' AND datavaluetypeid='CrdPrv'"
                    f"&$limit=50000"
                )
                results.append(
                    DatasetResult(
                        source=self.source_name,
                        id=did,
                        title=f"{full} — {geo_label}",
                        description=(
                            f"CDC PLACES {geo_label}-level crude prevalence for "
                            f'"{short}" ({cat}). '
                            f"Covers all US {geo_label.lower()}s with confidence intervals."
                        )[:500],
                        formats=["CSV"],
                        download_url=csv_url,
                        metadata={
                            "measureid": mid,
                            "category": cat,
                            "geo_level": geo_key,
                        },
                    )
                )
            if len(results) >= limit:
                break

        return results[:limit]

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Build a CSV download URL from an encoded dataset_id like 'county:CASTHMA'."""
        if ":" not in dataset_id:
            return None
        geo, mid = dataset_id.split(":", 1)
        ds = _DATASETS.get(geo)
        if not ds:
            return None
        socrata_id = ds[0]
        return (
            f"{BASE}/{socrata_id}.csv"
            f"?$where=measureid='{mid}' AND datavaluetypeid='CrdPrv'"
            f"&$limit=50000"
        )

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download CDC PLACES data as CSV."""
        url = await self.get_download_url(dataset_id)
        if not url:
            logger.warning("CDC PLACES: invalid dataset_id %r", dataset_id)
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_id = dataset_id.replace(":", "_")
        dest = dest_dir / f"cdc_places_{safe_id}.csv"

        try:
            await _client.stream_download(url, dest)
            if dest.stat().st_size < 50:
                logger.warning("CDC PLACES download too small for %s", dataset_id)
                dest.unlink(missing_ok=True)
                return None
            return dest
        except Exception as exc:
            logger.warning("CDC PLACES download failed for %s: %s", dataset_id, exc)
            return None
