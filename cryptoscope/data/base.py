"""Abstract base class for data providers."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, calls_per_minute: int) -> None:
        self._interval = 60.0 / calls_per_minute
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


class DataProvider(ABC):
    """Base class for all data providers."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        calls_per_minute: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._rate_limiter = RateLimiter(calls_per_minute)
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=15.0,
                headers=self._default_headers(),
            )
        return self._client

    def _default_headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make a rate-limited GET request."""
        await self._rate_limiter.acquire()
        logger.debug("GET %s%s params=%s", self.base_url, path, params)
        resp = await self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    @abstractmethod
    async def fetch_tickers(self, coin_ids: list[str]) -> list[Any]:
        """Fetch current ticker data for given coin IDs."""

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
