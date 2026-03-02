"""CoinGecko data provider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from cryptoscope.data.base import DataProvider
from cryptoscope.models.price import OHLCV, Ticker

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"


class CoinGeckoProvider(DataProvider):
    """CoinGecko free-tier API provider (30 calls/min)."""

    def __init__(self, api_key: str = "", currency: str = "usd") -> None:
        base_url = COINGECKO_PRO_BASE if api_key else COINGECKO_BASE
        super().__init__(base_url=base_url, api_key=api_key, calls_per_minute=30)
        self.currency = currency

    def _default_headers(self) -> dict[str, str]:
        headers = super()._default_headers()
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key
        return headers

    async def fetch_tickers(self, coin_ids: list[str]) -> list[Ticker]:
        """Fetch current market data for a list of coin IDs."""
        ids_str = ",".join(coin_ids)
        data = await self._get(
            "/coins/markets",
            params={
                "vs_currency": self.currency,
                "ids": ids_str,
                "order": "market_cap_desc",
                "per_page": len(coin_ids),
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
        )
        return [self._parse_ticker(item) for item in data]

    async def fetch_top_coins(self, limit: int = 25) -> list[Ticker]:
        """Fetch top N coins by market cap."""
        data = await self._get(
            "/coins/markets",
            params={
                "vs_currency": self.currency,
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
        )
        return [self._parse_ticker(item) for item in data]

    async def fetch_ohlcv(self, coin_id: str, days: int = 30) -> list[OHLCV]:
        """Fetch OHLCV data. days: 1, 7, 14, 30, 90, 180, 365, max."""
        data = await self._get(
            f"/coins/{coin_id}/ohlc",
            params={
                "vs_currency": self.currency,
                "days": str(days),
            },
        )
        return [
            OHLCV(
                timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                open=candle[1],
                high=candle[2],
                low=candle[3],
                close=candle[4],
                volume=0.0,  # OHLC endpoint doesn't include volume
            )
            for candle in data
        ]

    async def fetch_coin_list(self) -> list[dict]:
        """Fetch full coin index — id/symbol/name for every coin CoinGecko tracks.

        Returns a list of dicts: [{id, symbol, name}, ...].
        Callers should cache this — it rarely changes.
        """
        return await self._get(
            "/coins/list",
            params={"include_platform": "false"},
        )

    async def fetch_market_page(self, page: int = 1, per_page: int = 50) -> list[Ticker]:
        """Fetch a page of coins sorted by market cap."""
        data = await self._get(
            "/coins/markets",
            params={
                "vs_currency": self.currency,
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
        )
        return [self._parse_ticker(item) for item in data]

    async def fetch_coins_by_ids(self, coin_ids: list[str]) -> list[Ticker]:
        """Fetch market data for an explicit list of coin IDs (used for search results)."""
        if not coin_ids:
            return []
        data = await self._get(
            "/coins/markets",
            params={
                "vs_currency": self.currency,
                "ids": ",".join(coin_ids[:250]),
                "order": "market_cap_desc",
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "1h,24h,7d",
            },
        )
        return [self._parse_ticker(item) for item in data]

    async def fetch_coin_detail(self, coin_id: str) -> dict[str, Any]:
        """Fetch detailed info for a single coin."""
        return await self._get(
            f"/coins/{coin_id}",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
            },
        )

    def _parse_ticker(self, item: dict[str, Any]) -> Ticker:
        return Ticker(
            id=item["id"],
            symbol=item.get("symbol", "").upper(),
            name=item.get("name", ""),
            price_usd=item.get("current_price", 0) or 0,
            market_cap=item.get("market_cap", 0) or 0,
            volume_24h=item.get("total_volume", 0) or 0,
            change_1h=item.get("price_change_percentage_1h_in_currency", 0) or 0,
            change_24h=item.get("price_change_percentage_24h", 0) or 0,
            change_7d=item.get("price_change_percentage_7d_in_currency", 0) or 0,
            market_cap_rank=item.get("market_cap_rank", 0) or 0,
            circulating_supply=item.get("circulating_supply", 0) or 0,
            max_supply=item.get("max_supply"),
            ath=item.get("ath", 0) or 0,
            atl=item.get("atl", 0) or 0,
            last_updated=datetime.now(),
        )
