"""Harvard Dataverse API adapter for searching and downloading research datasets.

Uses the Dataverse Search API and Data Access API.
No authentication required for public datasets.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

BASE_URL = "https://dataverse.harvard.edu"
SEARCH_URL = f"{BASE_URL}/api/search"
TIMEOUT = 20.0


class HarvardDataverseSource:
    source_name: str = "harvard_dataverse"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        """Search Harvard Dataverse for datasets matching *query*."""
        params = {
            "q": query,
            "type": "dataset",
            "per_page": limit,
            "sort": "date",
            "order": "desc",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Harvard Dataverse search failed for query=%r: %s",
                query,
                exc,
            )
            return []

        data = body.get("data", {})
        items = data.get("items", [])

        results: list[DatasetResult] = []
        for item in items[:limit]:
            dataset_id = item.get("global_id", "")
            title = item.get("name", "")
            description = item.get("description", "")

            # Build download URL (ZIP of all files via persistent ID)
            download_url = None
            if dataset_id:
                download_url = (
                    f"{BASE_URL}/api/access/dataset/:persistentId/?persistentId={dataset_id}"
                )

            # Collect file format info from the file listing
            file_count = item.get("file_count", 0)
            subjects = item.get("subjects", [])
            published_at = item.get("published_at", "")

            results.append(
                DatasetResult(
                    source=self.source_name,
                    id=dataset_id,
                    title=title,
                    description=description[:500] if description else "",
                    formats=["ZIP"],
                    download_url=download_url,
                    metadata={
                        k: v
                        for k, v in {
                            "subjects": subjects or None,
                            "file_count": file_count or None,
                            "published_at": published_at or None,
                            "citation": item.get("citation"),
                        }.items()
                        if v is not None
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        """Return a download URL for the dataset (ZIP of all files)."""
        if not dataset_id:
            return None
        return f"{BASE_URL}/api/access/dataset/:persistentId/?persistentId={dataset_id}"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download dataset files from Harvard Dataverse.

        First tries to find and download individual CSV/TSV files.
        Falls back to downloading the full dataset ZIP.
        """
        if not dataset_id:
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(
                timeout=60,
                follow_redirects=True,
            ) as client:
                # Try to get individual files via dataset version API
                file_path = await _download_best_file(
                    client,
                    dataset_id,
                    dest_dir,
                )
                if file_path:
                    return file_path

                # Fallback: download full dataset as ZIP
                return await _download_zip(
                    client,
                    dataset_id,
                    dest_dir,
                )
        except (httpx.HTTPError, OSError) as exc:
            logger.warning(
                "Harvard Dataverse download failed for %s: %s",
                dataset_id,
                exc,
            )
            return None


async def _download_best_file(
    client: httpx.AsyncClient,
    dataset_id: str,
    dest_dir: Path,
) -> Path | None:
    """Try to download the best single tabular file from the dataset."""
    # List files in the dataset
    version_url = (
        f"{BASE_URL}/api/datasets/:persistentId/versions/"
        f":latest-published?persistentId={dataset_id}"
    )
    try:
        resp = await client.get(version_url)
        resp.raise_for_status()
        version_data = resp.json().get("data", {})
    except (httpx.HTTPError, ValueError):
        return None

    files = version_data.get("files", [])
    if not files:
        return None

    # Prefer CSV/TSV files, then tabular (Dataverse-ingested), then largest
    tabular_exts = {".csv", ".tsv", ".tab"}
    best_file = None
    best_size = -1

    for f in files:
        data_file = f.get("dataFile", {})
        filename = data_file.get("filename", "")
        file_id = data_file.get("id")
        file_size = data_file.get("filesize", 0)
        content_type = (data_file.get("contentType") or "").lower()

        if not file_id:
            continue

        ext = Path(filename).suffix.lower()
        is_tabular = ext in tabular_exts or "tab" in content_type
        is_csv_like = "csv" in content_type or ext == ".csv"

        # Score: CSV > other tabular > any file
        if is_csv_like:
            score = 3
        elif is_tabular:
            score = 2
        else:
            score = 1

        weighted = score * 1_000_000_000 + file_size
        if weighted > best_size:
            best_size = weighted
            best_file = (file_id, filename, content_type)

    if not best_file:
        return None

    file_id, filename, content_type = best_file
    # Download the file — use format=original for tabular files
    # to get CSV instead of Dataverse's tab-delimited format
    download_url = f"{BASE_URL}/api/access/datafile/{file_id}"
    params = {}
    if "tab-separated" in content_type or filename.endswith(".tab"):
        params["format"] = "original"

    resp = await client.get(download_url, params=params)
    resp.raise_for_status()

    # Sanitize filename
    safe_name = filename.replace("/", "_").replace("\\", "_")
    if not safe_name:
        safe_name = f"dataverse_{file_id}.csv"
    dest = dest_dir / safe_name

    dest.write_bytes(resp.content)
    return dest


async def _download_zip(
    client: httpx.AsyncClient,
    dataset_id: str,
    dest_dir: Path,
) -> Path | None:
    """Download the entire dataset as a ZIP file and extract it."""
    import zipfile

    zip_url = f"{BASE_URL}/api/access/dataset/:persistentId/?persistentId={dataset_id}"
    resp = await client.get(zip_url)
    resp.raise_for_status()

    zip_path = dest_dir / "dataverse_download.zip"
    zip_path.write_bytes(resp.content)

    # Extract and find the best data file
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest_dir)
    except zipfile.BadZipFile:
        # Maybe it was a single file, not a ZIP
        return zip_path if zip_path.stat().st_size > 0 else None
    finally:
        zip_path.unlink(missing_ok=True)

    # Pick the best extracted file
    data_files = [
        f
        for f in dest_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".csv", ".tsv", ".tab", ".json", ".parquet")
    ]
    if data_files:
        return max(data_files, key=lambda f: f.stat().st_size)

    # Fallback: largest file
    all_files = [f for f in dest_dir.iterdir() if f.is_file()]
    return max(all_files, key=lambda f: f.stat().st_size) if all_files else None
