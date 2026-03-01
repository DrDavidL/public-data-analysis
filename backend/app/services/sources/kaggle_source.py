from __future__ import annotations

import base64
import json
import logging
import os
import shutil
from pathlib import Path

import httpx

from app.config import settings
from app.schemas.datasets import DatasetResult

logger = logging.getLogger(__name__)

# Kaggle API for search (kagglehub doesn't expose search)
KAGGLE_API_URL = "https://www.kaggle.com/api/v1"
TIMEOUT = 20.0


def _ensure_token_env() -> bool:
    """Set KAGGLE_API_TOKEN env var so kagglehub picks it up."""
    if not settings.kaggle_api_token:
        return False
    os.environ["KAGGLE_API_TOKEN"] = settings.kaggle_api_token
    return True


def _auth_header() -> dict[str, str]:
    """Auth header for Kaggle REST API. Handles JSON token (Basic) or plain key (Bearer)."""
    token = settings.kaggle_api_token
    if not token:
        return {}
    # Token is typically JSON: {"username":"...","key":"..."}
    try:
        creds = json.loads(token)
        if isinstance(creds, dict) and "username" in creds and "key" in creds:
            encoded = base64.b64encode(f"{creds['username']}:{creds['key']}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: treat as a plain Bearer token
    return {"Authorization": f"Bearer {token}"}


class KaggleSource:
    source_name: str = "kaggle"

    async def search(self, query: str, limit: int = 5) -> list[DatasetResult]:
        if not settings.kaggle_api_token:
            logger.debug("Kaggle API token not configured, skipping")
            return []

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{KAGGLE_API_URL}/datasets/list",
                    params={
                        "search": query,
                        "fileType": "csv",
                        "page": 1,
                        "pageSize": limit,
                    },
                    headers=_auth_header(),
                )
                resp.raise_for_status()
                datasets = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Kaggle search failed: %s", exc)
            return []

        results: list[DatasetResult] = []
        for ds in datasets:
            ref: str = ds.get("ref", "")
            dataset_id = ref or str(ds.get("id", ""))

            results.append(
                DatasetResult(
                    source="kaggle",
                    id=dataset_id,
                    title=ds.get("title", ""),
                    description=ds.get("subtitle", "") or ds.get("description", ""),
                    formats=["CSV"],
                    size_bytes=ds.get("totalBytes"),
                    download_url=f"kaggle://{dataset_id}" if dataset_id else None,
                    metadata={
                        "usability_rating": ds.get("usabilityRating"),
                        "vote_count": ds.get("voteCount"),
                        "last_updated": ds.get("lastUpdated"),
                    },
                )
            )

        return results

    async def get_download_url(self, dataset_id: str) -> str | None:
        if not settings.kaggle_api_token or not dataset_id:
            return None
        return f"kaggle://{dataset_id}"

    async def download(self, dataset_id: str, dest_dir: Path) -> Path | None:
        """Download a Kaggle dataset using kagglehub."""
        if not _ensure_token_env():
            logger.debug("Kaggle API token not configured, skipping")
            return None

        if "/" not in dataset_id:
            logger.warning("Invalid Kaggle dataset id: %s", dataset_id)
            return None

        try:
            import kagglehub

            downloaded_path = kagglehub.dataset_download(dataset_id)
            downloaded = Path(downloaded_path)

            # Copy files to our session temp dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            if downloaded.is_dir():
                for f in downloaded.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dest_dir / f.name)
            elif downloaded.is_file():
                shutil.copy2(downloaded, dest_dir / downloaded.name)

            # Pick the largest data file — Kaggle archives often contain
            # multiple CSVs (data + notes/metadata) and the actual data
            # file is always the largest.
            data_files = [
                f
                for f in dest_dir.iterdir()
                if f.is_file() and f.suffix.lower() in (".csv", ".parquet", ".json")
            ]
            if data_files:
                return max(data_files, key=lambda f: f.stat().st_size)

            # Fallback: largest file of any type
            all_files = [f for f in dest_dir.iterdir() if f.is_file()]
            return max(all_files, key=lambda f: f.stat().st_size) if all_files else None

        except Exception as exc:
            logger.warning("Kaggle download failed for %s: %s", dataset_id, exc)
            return None
