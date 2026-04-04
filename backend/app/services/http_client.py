"""Shared async HTTP client with retry, circuit breaker, and disk caching.

All data source connectors should use ``get_client()`` for outbound requests.
This centralises retry/backoff logic, provides a per-source circuit breaker
to fast-fail when an upstream API is down, and optionally caches GET responses
on disk so repeated calls (common during development) avoid network round-trips.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import threading
import time
from typing import Any

import diskcache
import diskcache.core
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Disk cache (shared across all sources, 1-hour default TTL)
# Uses JSON serialization instead of pickle to mitigate CVE-2025-69872.
# ---------------------------------------------------------------------------
_CACHE_DIR = "/tmp/pubdata_http_cache"  # noqa: S108
DEFAULT_CACHE_TTL = 3600  # seconds


class _JSONDisk(diskcache.core.Disk):
    """Disk subclass that uses JSON instead of pickle for serialization."""

    def store(self, value: Any, read: bool, key: Any = diskcache.core.UNKNOWN) -> tuple:
        json_bytes = json.dumps(value, ensure_ascii=False, default=str).encode()
        return super().store(json_bytes, read, key=key)

    def fetch(self, mode: int, filename: str, value: Any, read: bool) -> Any:
        data = super().fetch(mode, filename, value, read)
        if isinstance(data, bytes):
            return json.loads(data)
        return data


_cache = diskcache.Cache(_CACHE_DIR, size_limit=500 * 1024 * 1024, disk=_JSONDisk)


def _cache_key(method: str, url: str, params: dict | None) -> str:
    raw = f"{method}:{url}:{sorted((params or {}).items())}"
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------
class _CBState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker for a single upstream source."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._lock = threading.Lock()
        self._state = _CBState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> str:
        with self._lock:
            if self._state is _CBState.OPEN:
                if time.monotonic() - self._last_failure_time >= self._recovery_timeout:
                    self._state = _CBState.HALF_OPEN
            return self._state.value

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = _CBState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                self._state = _CBState.OPEN

    @property
    def allow_request(self) -> bool:
        s = self.state  # triggers OPEN -> HALF_OPEN transition
        return s != _CBState.OPEN.value


# Per-source breakers (created lazily)
_breakers: dict[str, CircuitBreaker] = {}
_breaker_lock = threading.Lock()


def _get_breaker(source_name: str) -> CircuitBreaker:
    with _breaker_lock:
        if source_name not in _breakers:
            _breakers[source_name] = CircuitBreaker()
        return _breakers[source_name]


# ---------------------------------------------------------------------------
# Retry-enabled request helpers
# ---------------------------------------------------------------------------
_retry_decorator = retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


class SourceHTTPClient:
    """Async HTTP client scoped to a single data source.

    Usage::

        client = SourceHTTPClient("usaspending")
        data = await client.get_json("https://api.usaspending.gov/...", params={...})
    """

    def __init__(
        self,
        source_name: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ) -> None:
        self.source_name = source_name
        self.timeout = timeout
        self.headers = headers or {}
        self.cache_ttl = cache_ttl
        self._breaker = _get_breaker(source_name)

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> Any:
        """GET *url* and return parsed JSON, with caching and circuit breaker."""
        if not self._breaker.allow_request:
            logger.warning("Circuit breaker OPEN for %s, skipping request", self.source_name)
            raise httpx.HTTPStatusError(
                f"Circuit breaker open for {self.source_name}",
                request=httpx.Request("GET", url),
                response=httpx.Response(503),
            )

        # Check cache
        if use_cache:
            key = _cache_key("GET", url, params)
            cached = _cache.get(key)
            if cached is not None:
                return cached

        try:
            data = await self._do_get_json(url, params=params)
            self._breaker.record_success()
            if use_cache:
                _cache.set(key, data, expire=self.cache_ttl)
            return data
        except Exception:
            self._breaker.record_failure()
            raise

    @_retry_decorator
    async def _do_get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    async def stream_download(self, url: str, dest: str | Any) -> None:
        """Stream-download *url* to a file path, bypassing cache."""
        if not self._breaker.allow_request:
            raise httpx.HTTPStatusError(
                f"Circuit breaker open for {self.source_name}",
                request=httpx.Request("GET", url),
                response=httpx.Response(503),
            )
        try:
            async with httpx.AsyncClient(
                timeout=120, headers=self.headers, follow_redirects=True
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    from pathlib import Path

                    p = Path(dest)
                    with p.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            fh.write(chunk)
            self._breaker.record_success()
        except Exception:
            self._breaker.record_failure()
            raise

    async def post_json(
        self,
        url: str,
        *,
        json_body: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """POST with JSON body and return parsed JSON response."""
        if not self._breaker.allow_request:
            raise httpx.HTTPStatusError(
                f"Circuit breaker open for {self.source_name}",
                request=httpx.Request("POST", url),
                response=httpx.Response(503),
            )
        try:
            data = await self._do_post_json(url, json_body=json_body, params=params)
            self._breaker.record_success()
            return data
        except Exception:
            self._breaker.record_failure()
            raise

    @_retry_decorator
    async def _do_post_json(
        self,
        url: str,
        *,
        json_body: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.post(url, json=json_body, params=params)
            resp.raise_for_status()
            return resp.json()
