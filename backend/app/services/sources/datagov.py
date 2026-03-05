"""data.gov CKAN API adapter for searching public datasets."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

BASE_URL = "https://catalog.data.gov/api/3/action/package_search"
DOWNLOADABLE_FORMATS = {"csv", "json", "xls", "xlsx"}
TIMEOUT = 30.0


class DataGovSource:
    source_name: str = "data.gov"

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search data.gov for datasets matching *query*."""
        params: dict[str, str | int] = {"q": query, "rows": limit}
        headers = self._auth_headers()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(BASE_URL, params=params, headers=headers)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error(
                "data.gov search failed for query=%r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return []

        results: list[DatasetResult] = []
        for pkg in body.get("result", {}).get("results", []):
            formats = self._extract_formats(pkg)
            download_url = self._pick_download_url(pkg)
            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=pkg.get("id", ""),
                    title=pkg.get("title", ""),
                    description=pkg.get("notes", ""),
                    formats=formats,
                    download_url=download_url,
                    metadata={
                        "organization": (pkg.get("organization") or {}).get("title", ""),
                        "tags": [t.get("name", "") for t in pkg.get("tags", [])],
                        "license_title": pkg.get("license_title", ""),
                    },
                )
            )

        return results

    # ------------------------------------------------------------------
    # Download URL
    # ------------------------------------------------------------------

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Fetch the package and return the first CSV/JSON resource URL."""
        url = "https://catalog.data.gov/api/3/action/package_show"
        params: dict[str, str] = {"id": dataset_id}
        headers = self._auth_headers()

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                pkg = resp.json().get("result", {})
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("data.gov get_download_url failed for id=%r: %s", dataset_id, exc)
            return None

        return self._pick_download_url(pkg)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download the first downloadable resource to *dest_dir*."""
        download_url = await self.get_download_url(dataset_id)
        if not download_url:
            logger.warning("No downloadable URL found for dataset %s", dataset_id)
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
            logger.error("data.gov download failed for url=%r: %s", download_url, exc)
            return None

        return dest_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_formats(pkg: dict) -> list[str]:
        """Return de-duplicated list of downloadable formats in the package."""
        formats: list[str] = []
        seen: set[str] = set()
        for res in pkg.get("resources", []):
            fmt = (res.get("format") or "").upper()
            if fmt.lower() in DOWNLOADABLE_FORMATS and fmt not in seen:
                seen.add(fmt)
                formats.append(fmt)
        return formats

    @staticmethod
    def _pick_download_url(pkg: dict) -> str | None:
        """Return the URL of the first CSV or JSON resource, if any."""
        for preferred in ("csv", "json"):
            for res in pkg.get("resources", []):
                fmt = (res.get("format") or "").lower()
                if fmt == preferred and res.get("url"):
                    return res["url"]
        return None

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        """Return authorization headers when an API key is configured."""
        if settings.datagov_api_key:
            return {"X-CKAN-API-Key": settings.datagov_api_key}
        return {}
