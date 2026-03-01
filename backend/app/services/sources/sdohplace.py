"""SDOH Place metadata scraper adapter for health/social/demographics data."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from app.schemas.datasets import DatasetResult
from app.services.sources.base import extract_keywords as _extract_keywords

logger = logging.getLogger(__name__)

BASE_URL = "https://metadata.sdohplace.org"
TABLE_URL = f"{BASE_URL}/table"
RECORD_URL = f"{BASE_URL}/record"
RECORD_ID_RE = re.compile(r"/record/([\w-]+)")
TIMEOUT = 25.0
MAX_RETRIES = 2
CACHE_TTL_SECONDS = 3600  # 1 hour

SEARCHABLE_FIELDS = (
    "title",
    "description",
    "subject",
    "keyword",
    "theme",
    "data_variables",
)


class SDOHPlaceSource:
    source_name: str = "sdohplace"

    # Class-level cache shared across instances.
    _record_ids_cache: list[str] = []
    _cache_timestamp: float = 0.0

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search SDOH Place records matching *query*."""
        record_ids = await self._get_record_ids()
        if not record_ids:
            return []

        results: list[DatasetResult] = []
        query_lower = query.lower()

        for record_id in record_ids:
            if len(results) >= limit:
                break

            metadata = await self._fetch_record(record_id)
            if metadata is None:
                continue

            if self._matches_query(metadata, query_lower):
                results.append(self._to_dataset_result(record_id, metadata))

        return results

    # ------------------------------------------------------------------
    # Download URL
    # ------------------------------------------------------------------

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return the download URL for a specific record, if available."""
        metadata = await self._fetch_record(dataset_id)
        if metadata is None:
            return None
        return self._extract_download_url(metadata)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download the dataset file to *dest_dir*."""
        download_url = await self.get_download_url(dataset_id)
        if not download_url:
            logger.warning("No download URL found for SDOH Place record %s", dataset_id)
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = download_url.rsplit("/", 1)[-1] or f"{dataset_id}.csv"
        dest_path = dest_dir / filename

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
                async with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    with dest_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            fh.write(chunk)
        except httpx.HTTPError as exc:
            logger.error("SDOH Place download failed for url=%r: %s", download_url, exc)
            return None

        return dest_path

    # ------------------------------------------------------------------
    # Record index (cached)
    # ------------------------------------------------------------------

    async def _get_record_ids(self) -> list[str]:
        """Return all record IDs from the table page, using a 1-hour cache."""
        now = time.monotonic()
        if (
            SDOHPlaceSource._record_ids_cache
            and (now - SDOHPlaceSource._cache_timestamp) < CACHE_TTL_SECONDS
        ):
            return SDOHPlaceSource._record_ids_cache

        html = await self._request_with_retries(TABLE_URL)
        if html is None:
            return SDOHPlaceSource._record_ids_cache  # stale is better than empty

        soup = BeautifulSoup(html, "html.parser")
        ids: list[str] = []
        seen: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            match = RECORD_ID_RE.search(anchor["href"])
            if match and match.group(1) not in seen:
                seen.add(match.group(1))
                ids.append(match.group(1))

        if ids:
            SDOHPlaceSource._record_ids_cache = ids
            SDOHPlaceSource._cache_timestamp = now

        return ids

    # ------------------------------------------------------------------
    # Single record fetch
    # ------------------------------------------------------------------

    async def _fetch_record(self, record_id: str) -> dict | None:
        """Fetch JSON metadata for a single record."""
        url = f"{RECORD_URL}/{record_id}"
        body = await self._request_with_retries(url, params={"f": "json"})
        if body is None:
            return None

        try:
            return json.loads(body)
        except (ValueError, TypeError) as exc:
            logger.error("Failed to parse JSON for SDOH Place record %s: %s", record_id, exc)
            return None

    # ------------------------------------------------------------------
    # HTTP helper with retries
    # ------------------------------------------------------------------

    @staticmethod
    async def _request_with_retries(
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> str | None:
        """GET *url* with exponential-backoff retries.

        Returns the response text on success, or ``None`` on failure.
        """
        for attempt in range(1, MAX_RETRIES + 2):  # initial + retries
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    return resp.text
            except httpx.HTTPError as exc:
                if attempt > MAX_RETRIES:
                    logger.error(
                        "SDOH Place request failed after %d attempts for %s: %s",
                        attempt,
                        url,
                        exc,
                    )
                    return None
                delay = 2 ** (attempt - 1)  # 1s, 2s
                logger.warning(
                    "SDOH Place request attempt %d failed for %s: %s — retrying in %ds",
                    attempt,
                    url,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        return None  # unreachable, but keeps mypy happy

    # ------------------------------------------------------------------
    # Query matching
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_query(metadata: dict, query_lower: str) -> bool:
        """Return True if enough keywords from *query_lower* appear in searchable fields."""
        keywords = _extract_keywords(query_lower)
        if not keywords:
            return False

        # Combine all searchable text into one string
        text_parts: list[str] = []
        for field in SEARCHABLE_FIELDS:
            value = metadata.get(field)
            if value is None:
                continue
            if isinstance(value, str):
                text_parts.append(value.lower())
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        text_parts.append(item.lower())
        combined = " ".join(text_parts)

        hits = sum(1 for kw in keywords if kw in combined)
        # Require at least half of keywords to match (minimum 1)
        return hits >= max(1, len(keywords) // 2)

    # ------------------------------------------------------------------
    # Result construction
    # ------------------------------------------------------------------

    def _to_dataset_result(self, record_id: str, metadata: dict) -> DatasetResult:
        """Convert raw SDOH Place metadata into a ``DatasetResult``."""
        title = metadata.get("title", "")
        if isinstance(title, list):
            title = title[0] if title else ""

        description = metadata.get("description", "")
        if isinstance(description, list):
            description = " ".join(description)

        formats = self._extract_formats(metadata)
        download_url = self._extract_download_url(metadata)

        return DatasetResult(
            source=self.source_name,
            id=record_id,
            title=title,
            description=description,
            formats=formats,
            download_url=download_url,
            metadata={
                "subject": metadata.get("subject", []),
                "keyword": metadata.get("keyword", []),
                "theme": metadata.get("theme", []),
                "data_variables": metadata.get("data_variables", []),
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_download_url(metadata: dict) -> str | None:
        """Extract the first download URL from distribution metadata."""
        distributions = metadata.get("distribution", [])
        if isinstance(distributions, dict):
            distributions = [distributions]

        for dist in distributions:
            if not isinstance(dist, dict):
                continue
            url = dist.get("downloadURL") or dist.get("downloadUrl")
            if url:
                return url
            # Fall back to accessURL if no downloadURL is present.
            url = dist.get("accessURL") or dist.get("accessUrl")
            if url:
                return url

        return None

    @staticmethod
    def _extract_formats(metadata: dict) -> list[str]:
        """Extract unique format strings from distribution metadata."""
        formats: list[str] = []
        seen: set[str] = set()
        distributions = metadata.get("distribution", [])
        if isinstance(distributions, dict):
            distributions = [distributions]

        for dist in distributions:
            if not isinstance(dist, dict):
                continue
            fmt = dist.get("mediaType") or dist.get("format") or ""
            if isinstance(fmt, str) and fmt:
                # Normalize: "text/csv" -> "CSV", "application/json" -> "JSON"
                normalized = fmt.rsplit("/", 1)[-1].upper()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    formats.append(normalized)

        return formats
