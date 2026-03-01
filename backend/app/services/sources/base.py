from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from app.schemas.datasets import DatasetResult

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "shall",
        "and",
        "or",
        "but",
        "not",
        "no",
        "nor",
        "what",
        "which",
        "who",
        "whom",
        "how",
        "when",
        "where",
        "why",
        "this",
        "that",
        "these",
        "those",
        "i",
        "we",
        "you",
        "they",
        "it",
        "its",
        "my",
        "your",
        "our",
        "their",
        "his",
        "her",
        "across",
        "between",
        "through",
        "about",
        "into",
        "over",
        "want",
        "explore",
        "show",
        "find",
        "get",
        "see",
        "look",
    }
)


def extract_keywords(query: str) -> list[str]:
    """Extract meaningful search terms from a natural language query."""
    words = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1][:8]


class DataSource(Protocol):
    source_name: str

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]: ...

    async def get_download_url(self, dataset_id: str) -> str | None: ...

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None: ...
