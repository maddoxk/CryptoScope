"""CryptoPanic news feed provider."""

from __future__ import annotations

import logging
from datetime import datetime

from cryptoscope.data.base import DataProvider
from cryptoscope.models.sentiment import NewsItem

logger = logging.getLogger(__name__)

CRYPTOPANIC_API = "https://cryptopanic.com/api/free/v1"


class CryptoPanicProvider(DataProvider):
    """CryptoPanic aggregated crypto news (API key required for full access)."""

    def __init__(self, api_key: str = "") -> None:
        super().__init__(base_url=CRYPTOPANIC_API, api_key=api_key, calls_per_minute=10)

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        """Not applicable for this provider."""
        return []

    async def fetch_news(
        self,
        currencies: str = "",
        filter_type: str = "hot",
        limit: int = 20,
    ) -> list[NewsItem]:
        """Fetch news articles.

        filter_type: rising, hot, bullish, bearish, important, lol
        currencies: comma-separated symbols (BTC, ETH)
        """
        params: dict = {"auth_token": self.api_key} if self.api_key else {}
        if currencies:
            params["currencies"] = currencies
        if filter_type:
            params["filter"] = filter_type

        try:
            data = await self._get("/posts/", params=params)
        except Exception as e:
            logger.warning("CryptoPanic fetch failed (API key may be needed): %s", e)
            return []

        results = data.get("results", [])
        items = []
        for item in results[:limit]:
            items.append(self._parse_item(item))
        return items

    def _parse_item(self, item: dict) -> NewsItem:
        # Parse published date
        pub_str = item.get("published_at", "")
        try:
            published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            # Convert to naive local for display
            published_at = published_at.replace(tzinfo=None)
        except (ValueError, AttributeError):
            published_at = datetime.now()

        # Extract sentiment from votes
        votes = item.get("votes", {})
        positive = votes.get("positive", 0)
        negative = votes.get("negative", 0)
        if positive > negative:
            sentiment = "bullish"
        elif negative > positive:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        # Extract coin symbols
        coins = []
        for currency in item.get("currencies", []):
            code = currency.get("code", "")
            if code:
                coins.append(code)

        source_info = item.get("source", {})
        source_title = source_info.get("title", "Unknown") if isinstance(source_info, dict) else "Unknown"

        return NewsItem(
            title=item.get("title", "No title"),
            source=source_title,
            url=item.get("url", ""),
            published_at=published_at,
            sentiment=sentiment,
            coins=coins,
        )
