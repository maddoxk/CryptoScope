"""Alternative.me Fear and Greed Index provider."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from cryptoscope.data.base import DataProvider
from cryptoscope.models.sentiment import FearGreedEntry

logger = logging.getLogger(__name__)

FEAR_GREED_API = "https://api.alternative.me"


class FearGreedProvider(DataProvider):
    """Fear and Greed Index from Alternative.me (no auth required)."""

    def __init__(self) -> None:
        super().__init__(base_url=FEAR_GREED_API, calls_per_minute=30)

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        """Not applicable for this provider."""
        return []

    async def fetch_current(self) -> FearGreedEntry | None:
        """Fetch the current Fear and Greed Index value."""
        data = await self._get("/fng/", params={"limit": "1"})
        entries = data.get("data", [])
        if not entries:
            return None
        return self._parse_entry(entries[0])

    async def fetch_history(self, days: int = 30) -> list[FearGreedEntry]:
        """Fetch historical Fear and Greed values."""
        data = await self._get("/fng/", params={"limit": str(days)})
        entries = data.get("data", [])
        return [self._parse_entry(e) for e in entries]

    def _parse_entry(self, item: dict) -> FearGreedEntry:
        value = int(item.get("value", 50))
        classification = item.get("value_classification", self._classify(value))
        timestamp = datetime.fromtimestamp(
            int(item.get("timestamp", 0)), tz=timezone.utc
        )
        return FearGreedEntry(
            value=value,
            classification=classification,
            timestamp=timestamp,
        )

    @staticmethod
    def _classify(value: int) -> str:
        if value <= 20:
            return "Extreme Fear"
        elif value <= 40:
            return "Fear"
        elif value <= 60:
            return "Neutral"
        elif value <= 80:
            return "Greed"
        return "Extreme Greed"
