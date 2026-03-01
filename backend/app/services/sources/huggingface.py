"""HuggingFace Hub adapter for searching and downloading public datasets."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

_BASE_URL = "https://huggingface.co/api/datasets"
_TIMEOUT = httpx.Timeout(15.0)


class HuggingFaceSource:
    """Implements the DataSource protocol for HuggingFace Hub."""

    source_name: str = "huggingface"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search HuggingFace Hub for datasets matching *query*."""
        params = {
            "search": query,
            "limit": limit,
            "sort": "downloads",
            "direction": "-1",
        }
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                items: list[dict] = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("HuggingFace search failed for query=%r: %s", query, exc)
            return []

        results: list[DatasetResult] = []
        for item in items:
            dataset_id: str = item.get("id", "")
            description = (
                item.get("description") or item.get("cardData", {}).get("description", "") or ""
            )
            tags: list[str] = item.get("tags", [])

            # Extract available formats from tags (e.g. "format:parquet")
            formats = [t.split(":", 1)[1] for t in tags if t.startswith("format:")]
            # Determine a sensible default format for the download URL
            download_url = self._parquet_api_url(dataset_id)

            size_bytes = (
                item.get("cardData", {}).get("dataset_size")
                if isinstance(item.get("cardData"), dict)
                else None
            )

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=dataset_id,
                    title=dataset_id,
                    description=description,
                    formats=formats,
                    size_bytes=size_bytes,
                    download_url=download_url,
                    metadata={
                        "downloads": item.get("downloads", 0),
                        "likes": item.get("likes", 0),
                        "tags": tags,
                        "last_modified": item.get("lastModified", ""),
                    },
                )
            )
        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return the parquet endpoint URL for *dataset_id*, or ``None`` on failure."""
        url = self._parquet_api_url(dataset_id)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.head(url)
                if resp.status_code < 400:
                    return url
        except httpx.HTTPError as exc:
            logger.warning("HuggingFace download-url check failed for %s: %s", dataset_id, exc)
        return None

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download parquet/csv files for *dataset_id* into *dest_dir*.

        Returns the path to the downloaded file, or ``None`` on failure.
        """
        parquet_url = self._parquet_api_url(dataset_id)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                # First, resolve the parquet endpoint to get actual file URLs
                resp = await client.get(parquet_url)
                resp.raise_for_status()
                parquet_info = resp.json()

                # The parquet API returns a mapping of split -> list of file URLs.
                # Grab the first available file.
                file_url = self._first_file_url(parquet_info)
                if file_url is None:
                    logger.warning("No downloadable files found for %s", dataset_id)
                    return None

                # Stream-download the file
                dest_dir.mkdir(parents=True, exist_ok=True)
                filename = file_url.rsplit("/", 1)[-1] or f"{dataset_id.replace('/', '_')}.parquet"
                dest_path = dest_dir / filename

                async with client.stream("GET", file_url) as stream:
                    stream.raise_for_status()
                    with dest_path.open("wb") as fh:
                        async for chunk in stream.aiter_bytes(chunk_size=1024 * 64):
                            fh.write(chunk)

        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.warning("HuggingFace download failed for %s: %s", dataset_id, exc)
            return None

        logger.info("Downloaded %s to %s", dataset_id, dest_path)
        return dest_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parquet_api_url(dataset_id: str) -> str:
        return f"{_BASE_URL}/{dataset_id}/parquet"

    @staticmethod
    def _first_file_url(parquet_info: dict | list) -> str | None:
        """Extract the first downloadable URL from the parquet API response.

        The response shape varies: it can be a dict mapping config names to
        split mappings (``{config: {split: [urls]}}``) or a flat list of URLs.
        """
        if isinstance(parquet_info, list):
            for entry in parquet_info:
                if isinstance(entry, str):
                    return entry
                if isinstance(entry, dict) and "url" in entry:
                    return entry["url"]
            return None

        if isinstance(parquet_info, dict):
            for config in parquet_info.values():
                if isinstance(config, dict):
                    for split_files in config.values():
                        if isinstance(split_files, list):
                            for entry in split_files:
                                if isinstance(entry, str):
                                    return entry
                                if isinstance(entry, dict) and "url" in entry:
                                    return entry["url"]
                elif isinstance(config, list):
                    for entry in config:
                        if isinstance(entry, str):
                            return entry
                        if isinstance(entry, dict) and "url" in entry:
                            return entry["url"]
        return None
