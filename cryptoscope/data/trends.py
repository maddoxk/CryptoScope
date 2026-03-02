"""Google Trends provider using pytrends (optional dependency)."""

from __future__ import annotations

import logging
from datetime import datetime

from cryptoscope.models.sentiment import TrendingTopic

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = ["bitcoin", "ethereum", "crypto", "solana", "defi"]


class GoogleTrendsProvider:
    """Google Trends search interest tracker.

    Uses pytrends if available, otherwise returns empty data gracefully.
    """

    def __init__(self) -> None:
        self._pytrends = None
        try:
            from pytrends.request import TrendReq
            self._pytrends = TrendReq(hl="en-US", tz=360)
        except ImportError:
            logger.info("pytrends not installed — Google Trends data unavailable")

    @property
    def available(self) -> bool:
        return self._pytrends is not None

    async def fetch_interest(
        self,
        keywords: list[str] | None = None,
        timeframe: str = "now 7-d",
    ) -> list[TrendingTopic]:
        """Fetch search interest for keywords.

        timeframe: 'now 7-d', 'today 3-m', 'today 12-m'
        """
        if not self.available:
            return []

        keywords = keywords or DEFAULT_KEYWORDS
        # pytrends supports max 5 keywords at a time
        keywords = keywords[:5]

        try:
            import asyncio

            # pytrends is synchronous, run in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._fetch_sync, keywords, timeframe)
            return result
        except Exception as e:
            logger.warning("Google Trends fetch failed: %s", e)
            return []

    def _fetch_sync(self, keywords: list[str], timeframe: str) -> list[TrendingTopic]:
        """Synchronous fetch of trend data."""
        self._pytrends.build_payload(keywords, timeframe=timeframe)
        df = self._pytrends.interest_over_time()

        if df.empty:
            return []

        topics = []
        for keyword in keywords:
            if keyword not in df.columns:
                continue
            series = df[keyword]
            current = float(series.iloc[-1])
            avg_30d = float(series.mean())

            change_pct = 0.0
            if avg_30d > 0:
                change_pct = ((current - avg_30d) / avg_30d) * 100

            is_spike = current > (avg_30d * 2) if avg_30d > 0 else False

            topics.append(TrendingTopic(
                term=keyword,
                interest=current,
                change_pct=change_pct,
                is_spike=is_spike,
            ))

        return topics
