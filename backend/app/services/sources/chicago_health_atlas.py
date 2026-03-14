"""Chicago Health Atlas / CDPH adapter.

Uses the Chicago Health Atlas API v1 at chicagohealthatlas.org/api/v1.
No authentication required. Covers 450+ health indicators for Chicago
community areas, ZIP codes, and census tracts.

Data source: https://chicagohealthatlas.org/download
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://chicagohealthatlas.org/api/v1"
TIMEOUT = 20.0
_CACHE_TTL = 3600  # 1 hour

# In-memory cache for all topics
_topics_cache: list[dict] | None = None
_topics_cache_ts: float = 0.0


async def _get_all_topics() -> list[dict]:
    """Fetch and cache all topics from the Chicago Health Atlas API."""
    global _topics_cache, _topics_cache_ts

    if _topics_cache is not None and (time.time() - _topics_cache_ts) < _CACHE_TTL:
        return _topics_cache

    all_topics: list[dict] = []
    url = f"{BASE_URL}/topics/?format=json&limit=100"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            while url:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()
                results = payload.get("results", [])
                all_topics.extend(results)
                url = payload.get("next")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Chicago Health Atlas topics fetch failed: %s", exc)
        return _topics_cache or []

    _topics_cache = all_topics
    _topics_cache_ts = time.time()
    logger.info("Cached %d Chicago Health Atlas topics", len(all_topics))
    return all_topics


def _score_topic(topic: dict, keywords: list[str]) -> int:
    """Score a topic by how many keywords match its name, description, and keywords."""
    name = (topic.get("name") or "").lower()
    desc = (topic.get("description") or "").lower()
    kw_field = (topic.get("keywords") or "").lower()
    subcats = ""
    for sc in topic.get("subcategories") or []:
        subcats += f" {(sc.get('name') or '').lower()}"
        cat = sc.get("category") or {}
        subcats += f" {(cat.get('name') or '').lower()}"

    searchable = f"{name} {desc} {kw_field} {subcats}"
    return sum(1 for kw in keywords if kw in searchable)


class ChicagoHealthAtlasSource:
    source_name: str = "chicago_health_atlas"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search Chicago Health Atlas topics by keyword matching."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        topics = await _get_all_topics()
        if not topics:
            return []

        scored: list[tuple[int, dict]] = []
        min_hits = max(1, len(keywords) // 2)

        for topic in topics:
            score = _score_topic(topic, keywords)
            if score >= min_hits:
                scored.append((score, topic))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[DatasetResult] = []
        for _score, topic in scored[:limit]:
            key = topic.get("key", "")
            name = topic.get("name", "")
            desc = topic.get("description", "") or ""
            units = topic.get("units", "")

            # Build description with metadata
            parts = [desc]
            if units:
                parts.append(f"Units: {units}")
            datasets = topic.get("datasets") or []
            if datasets:
                ds_name = datasets[0].get("name", "")
                if ds_name:
                    parts.append(f"Source: {ds_name}")
            subcats = topic.get("subcategories") or []
            if subcats:
                cat_names = []
                for sc in subcats:
                    cat = sc.get("category", {})
                    cat_name = cat.get("name", "")
                    sc_name = sc.get("name", "")
                    if cat_name and sc_name:
                        cat_names.append(f"{cat_name} > {sc_name}")
                if cat_names:
                    parts.append(f"Category: {', '.join(cat_names)}")

            full_desc = " | ".join(p for p in parts if p)

            # Download URL points to the topic API endpoint
            download_url = f"{BASE_URL}/topics/{key}/?format=json"

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=key,
                    title=f"Chicago Health: {name}",
                    description=full_desc[:500],
                    formats=["CSV"],
                    download_url=download_url,
                    metadata={
                        k: v
                        for k, v in {
                            "units": units,
                            "keywords": topic.get("keywords"),
                            "direction": topic.get("direction"),
                            "is_count": topic.get("is_count"),
                        }.items()
                        if v is not None
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return the API URL for fetching topic data."""
        if not dataset_id:
            return None
        return f"{BASE_URL}/topics/{dataset_id}/?format=json"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download Chicago Health Atlas indicator data as CSV.

        Fetches all related health indicators in the same subcategory
        to provide a rich dataset for comparative analysis.
        """
        if not dataset_id:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", dataset_id)[:100]
        dest = dest_dir / f"chicago_health_{safe_name}.csv"

        topics = await _get_all_topics()
        if not topics:
            return None

        # Find the target topic
        target = None
        for t in topics:
            if t.get("key") == dataset_id:
                target = t
                break

        if not target:
            logger.warning("Chicago Health Atlas topic %s not found", dataset_id)
            return None

        # Collect all topics sharing any subcategory with the target
        target_subcats = {sc.get("name", "") for sc in (target.get("subcategories") or [])}

        rows: list[str] = []
        cols = [
            "topic_key",
            "topic_name",
            "description",
            "units",
            "category",
            "subcategory",
            "keywords",
            "direction",
            "is_count",
        ]
        rows.append(",".join(cols))

        for t in topics:
            t_subcats = {sc.get("name", "") for sc in (t.get("subcategories") or [])}
            if not (t_subcats & target_subcats):
                continue

            t_desc = (t.get("description") or "").replace('"', '""')
            t_kw = (t.get("keywords") or "").replace('"', '""')
            t_name = (t.get("name") or "").replace('"', '""')
            t_cat = ""
            t_sc = ""
            t_subcats_list = t.get("subcategories") or []
            if t_subcats_list:
                t_sc = t_subcats_list[0].get("name", "")
                t_cat = (t_subcats_list[0].get("category") or {}).get("name", "")

            row = (
                f'"{t.get("key", "")}","{t_name}",'
                f'"{t_desc}","{t.get("units", "")}",'
                f'"{t_cat}","{t_sc}","{t_kw}",'
                f'"{t.get("direction", "")}","{t.get("is_count", "")}"'
            )
            rows.append(row)

        if len(rows) < 2:
            logger.warning("No data rows for Chicago Health Atlas topic %s", dataset_id)
            return None

        try:
            dest.write_text("\n".join(rows), encoding="utf-8")
        except OSError as exc:
            logger.warning("Chicago Health Atlas write failed for %s: %s", dataset_id, exc)
            return None

        return dest
