"""Lightweight cross-source search index for cached dataset metadata."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.services.sources.base import extract_keywords
from app.services.sources.sdohplace import SDOHPlaceSource
from app.services.sources.worldbank import WorldBankSource

logger = logging.getLogger(__name__)


@dataclass
class IndexEntry:
    source: str
    id: str
    title: str
    description: str
    keywords_text: str
    score: float = 0.0


class SourceIndex:
    """Aggregates metadata from cached sources for fast cross-source keyword search."""

    INDEX_TTL = 3600  # 1 hour

    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []
        self._timestamp: float = 0.0

    async def refresh(self) -> None:
        """Rebuild the index from cached sources if stale."""
        now = time.monotonic()
        if self._entries and (now - self._timestamp) < self.INDEX_TTL:
            return

        entries: list[IndexEntry] = []
        entries.extend(self._index_worldbank())
        entries.extend(self._index_sdohplace())

        if entries:
            self._entries = entries
            self._timestamp = now
            logger.info("Source index refreshed (%d entries)", len(entries))

    @staticmethod
    def _index_worldbank() -> list[IndexEntry]:
        """Build index entries from the World Bank indicators cache."""
        entries: list[IndexEntry] = []
        for ind in WorldBankSource._indicators_cache:
            name = ind.get("name", "")
            note = ind.get("sourceNote", "")
            code = ind.get("id", "")
            topics = " ".join(
                t.get("value", "") for t in ind.get("topics", []) if t.get("value")
            )
            keywords_text = f"{name} {note} {topics}".lower()
            entries.append(
                IndexEntry(
                    source="worldbank",
                    id=code,
                    title=name,
                    description=note[:500] if note else "",
                    keywords_text=keywords_text,
                )
            )
        return entries

    @staticmethod
    def _index_sdohplace() -> list[IndexEntry]:
        """Build index entries from the SDOH Place metadata cache."""
        entries: list[IndexEntry] = []
        for record_id, meta in SDOHPlaceSource._metadata_cache.items():
            title = meta.get("title", "")
            if isinstance(title, list):
                title = title[0] if title else ""

            description = meta.get("description", "")
            if isinstance(description, list):
                description = " ".join(description)

            text_parts: list[str] = [title.lower(), description.lower()]
            for fld in ("subject", "keyword", "theme", "data_variables"):
                val = meta.get(fld)
                if isinstance(val, str):
                    text_parts.append(val.lower())
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            text_parts.append(item.lower())

            entries.append(
                IndexEntry(
                    source="sdohplace",
                    id=record_id,
                    title=title,
                    description=description[:500] if description else "",
                    keywords_text=" ".join(text_parts),
                )
            )
        return entries

    def search(self, query: str, limit: int = 10) -> list[IndexEntry]:
        """Score and return top matching entries for *query*."""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        scored: list[IndexEntry] = []
        for entry in self._entries:
            hits = sum(1 for kw in keywords if kw in entry.keywords_text)
            if hits > 0:
                entry.score = hits / len(keywords)
                scored.append(entry)

        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:limit]
