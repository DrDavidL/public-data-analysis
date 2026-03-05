"""Tests for local metadata caching in World Bank, SDOH Place, and the cross-source index."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.source_index import SourceIndex
from app.services.sources.sdohplace import SDOHPlaceSource
from app.services.sources.worldbank import WorldBankSource

# ---------------------------------------------------------------------------
# Fixtures — reset class-level caches between tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_caches():
    """Clear all class-level caches before each test."""
    WorldBankSource._indicators_cache = []
    WorldBankSource._indicators_timestamp = 0.0

    SDOHPlaceSource._record_ids_cache = []
    SDOHPlaceSource._cache_timestamp = 0.0
    SDOHPlaceSource._metadata_cache = {}
    SDOHPlaceSource._metadata_timestamp = 0.0
    yield


# ---------------------------------------------------------------------------
# World Bank indicator cache
# ---------------------------------------------------------------------------

SAMPLE_INDICATORS = [
    {"id": "NY.GDP.MKTP.CD", "name": "GDP (current US$)", "sourceNote": "GDP note", "topics": []},
    {"id": "SP.POP.TOTL", "name": "Population, total", "sourceNote": "Pop note", "topics": []},
]


class TestWorldBankCache:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_api(self):
        """First call should fetch from API and populate cache."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"page": 1}, SAMPLE_INDICATORS]
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        result = await WorldBankSource._get_all_indicators(mock_client)

        assert len(result) == 2
        assert WorldBankSource._indicators_cache == SAMPLE_INDICATORS
        mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api(self):
        """Second call within TTL should return cached data without API call."""
        WorldBankSource._indicators_cache = SAMPLE_INDICATORS
        WorldBankSource._indicators_timestamp = time.monotonic()

        mock_client = AsyncMock()
        result = await WorldBankSource._get_all_indicators(mock_client)

        assert result == SAMPLE_INDICATORS
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_fallback_on_api_failure(self):
        """If API fails, return stale cache instead of empty."""
        WorldBankSource._indicators_cache = SAMPLE_INDICATORS
        WorldBankSource._indicators_timestamp = 0.0  # expired

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("API down"))

        result = await WorldBankSource._get_all_indicators(mock_client)

        assert result == SAMPLE_INDICATORS


# ---------------------------------------------------------------------------
# SDOH Place metadata cache
# ---------------------------------------------------------------------------

SAMPLE_SDOH_META = {
    "rec-1": {"title": "Food Access", "description": "Food desert data", "subject": ["health"]},
    "rec-2": {
        "title": "Housing Index",
        "description": "Housing affordability",
        "keyword": ["housing"],
    },
}


class TestSDOHPlaceMetadataCache:
    @pytest.mark.asyncio
    async def test_load_all_metadata_populates_cache(self):
        """_load_all_metadata should fetch all records and cache them."""
        record_ids = list(SAMPLE_SDOH_META.keys())

        async def mock_fetch(rid):
            return SAMPLE_SDOH_META.get(rid)

        with patch.object(SDOHPlaceSource, "_fetch_record_raw", side_effect=mock_fetch):
            await SDOHPlaceSource._load_all_metadata(record_ids)

        assert len(SDOHPlaceSource._metadata_cache) == 2
        assert SDOHPlaceSource._metadata_cache["rec-1"]["title"] == "Food Access"

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self):
        """When cache is fresh, _load_all_metadata should be a no-op."""
        SDOHPlaceSource._metadata_cache = dict(SAMPLE_SDOH_META)
        SDOHPlaceSource._metadata_timestamp = time.monotonic()

        with patch.object(SDOHPlaceSource, "_fetch_record_raw") as mock:
            await SDOHPlaceSource._load_all_metadata(["rec-1", "rec-2"])
            mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_record_uses_cache(self):
        """_fetch_record should return cached data without HTTP call."""
        SDOHPlaceSource._metadata_cache = {"rec-1": SAMPLE_SDOH_META["rec-1"]}

        source = SDOHPlaceSource()
        result = await source._fetch_record("rec-1")

        assert result["title"] == "Food Access"

    @pytest.mark.asyncio
    async def test_fetch_record_cache_miss_fetches(self):
        """_fetch_record on a cache miss should fetch and store."""
        source = SDOHPlaceSource()

        async def mock_fetch(rid):
            return SAMPLE_SDOH_META.get(rid)

        with patch.object(SDOHPlaceSource, "_fetch_record_raw", side_effect=mock_fetch):
            result = await source._fetch_record("rec-2")

        assert result["title"] == "Housing Index"
        assert "rec-2" in SDOHPlaceSource._metadata_cache


# ---------------------------------------------------------------------------
# Cross-source search index
# ---------------------------------------------------------------------------


class TestSourceIndex:
    @pytest.mark.asyncio
    async def test_refresh_builds_index(self):
        """Index should populate from World Bank and SDOH Place caches."""
        WorldBankSource._indicators_cache = SAMPLE_INDICATORS
        SDOHPlaceSource._metadata_cache = dict(SAMPLE_SDOH_META)

        index = SourceIndex()
        await index.refresh()

        assert len(index._entries) == len(SAMPLE_INDICATORS) + len(SAMPLE_SDOH_META)

    @pytest.mark.asyncio
    async def test_search_scoring(self):
        """Search should score and rank entries by keyword hits."""
        WorldBankSource._indicators_cache = SAMPLE_INDICATORS
        SDOHPlaceSource._metadata_cache = dict(SAMPLE_SDOH_META)

        index = SourceIndex()
        await index.refresh()

        results = index.search("GDP growth")
        assert len(results) > 0
        assert results[0].source == "worldbank"
        assert "GDP" in results[0].title

    @pytest.mark.asyncio
    async def test_search_no_keywords(self):
        """Search with only stop words should return empty."""
        index = SourceIndex()
        await index.refresh()

        results = index.search("the and or")
        assert results == []

    @pytest.mark.asyncio
    async def test_refresh_is_noop_when_fresh(self):
        """Refresh within TTL should not rebuild."""
        WorldBankSource._indicators_cache = SAMPLE_INDICATORS
        index = SourceIndex()
        await index.refresh()

        initial_entries = index._entries
        WorldBankSource._indicators_cache = []  # clear source
        await index.refresh()  # should be no-op

        assert index._entries is initial_entries
