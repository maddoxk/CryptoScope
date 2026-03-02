"""Sentiment and social data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FearGreedEntry:
    """Single Fear and Greed Index reading."""

    value: int  # 0-100
    classification: str  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    timestamp: datetime

    @property
    def color(self) -> str:
        if self.value <= 20:
            return "red"
        elif self.value <= 40:
            return "orange1"
        elif self.value <= 60:
            return "yellow"
        elif self.value <= 80:
            return "green_yellow"
        return "green"


@dataclass
class NewsItem:
    """Single news article from CryptoPanic."""

    title: str
    source: str
    url: str
    published_at: datetime
    sentiment: str = "neutral"  # bullish, bearish, neutral
    coins: list[str] = field(default_factory=list)

    @property
    def sentiment_color(self) -> str:
        if self.sentiment == "bullish":
            return "green"
        elif self.sentiment == "bearish":
            return "red"
        return "dim"

    @property
    def time_ago(self) -> str:
        delta = datetime.now() - self.published_at
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        return f"{seconds // 86400}d ago"


@dataclass
class SocialMetrics:
    """Social media metrics for a coin."""

    coin_id: str
    symbol: str
    mentions_24h: int = 0
    engagement_score: float = 0.0
    sentiment_bullish_pct: float = 0.0
    galaxy_score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TrendingTopic:
    """A trending search term or topic."""

    term: str
    interest: float  # Relative interest score
    change_pct: float = 0.0  # Change vs baseline
    is_spike: bool = False
