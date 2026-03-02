"""LunarCrush social metrics provider."""

from __future__ import annotations

import logging
from datetime import datetime

from cryptoscope.data.base import DataProvider
from cryptoscope.models.sentiment import SocialMetrics

logger = logging.getLogger(__name__)

LUNARCRUSH_API = "https://lunarcrush.com/api4/public"


class LunarCrushProvider(DataProvider):
    """LunarCrush social engagement and sentiment data."""

    def __init__(self, api_key: str = "") -> None:
        super().__init__(base_url=LUNARCRUSH_API, api_key=api_key, calls_per_minute=30)

    def _default_headers(self) -> dict[str, str]:
        headers = super()._default_headers()
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        """Not applicable for this provider."""
        return []

    async def fetch_social_metrics(self, symbols: list[str]) -> list[SocialMetrics]:
        """Fetch social metrics for given coin symbols (e.g., BTC, ETH)."""
        metrics = []
        for symbol in symbols:
            try:
                data = await self._get(
                    f"/coins/{symbol.lower()}/v1",
                )
                parsed = self._parse_metrics(symbol, data)
                if parsed:
                    metrics.append(parsed)
            except Exception as e:
                logger.warning("LunarCrush fetch failed for %s: %s", symbol, e)
        return metrics

    async def fetch_coin_summary(self, symbol: str) -> SocialMetrics | None:
        """Fetch social summary for a single coin."""
        try:
            data = await self._get(f"/coins/{symbol.lower()}/v1")
            return self._parse_metrics(symbol, data)
        except Exception as e:
            logger.warning("LunarCrush coin summary failed for %s: %s", symbol, e)
            return None

    def _parse_metrics(self, symbol: str, data: dict) -> SocialMetrics | None:
        if not data or "data" not in data:
            # Try parsing top-level
            coin_data = data
        else:
            coin_data = data.get("data", {})

        if not coin_data:
            return None

        return SocialMetrics(
            coin_id=symbol.lower(),
            symbol=symbol.upper(),
            mentions_24h=int(coin_data.get("social_mentions_24h", 0) or 0),
            engagement_score=float(coin_data.get("social_interactions_24h", 0) or 0),
            sentiment_bullish_pct=float(coin_data.get("sentiment", 0) or 0),
            galaxy_score=float(coin_data.get("galaxy_score", 0) or 0),
            timestamp=datetime.now(),
        )
