"""Reddit sentiment provider using public JSON API (no OAuth needed)."""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timezone

from cryptoscope.data.base import DataProvider
from cryptoscope.models.sentiment import SocialMetrics, TrendingTopic

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"

# Simple keyword sentiment lists
BULLISH_WORDS = {
    "bull", "bullish", "moon", "pump", "buy", "long", "breakout", "rally",
    "accumulate", "hodl", "undervalued", "ath", "gains", "rocket", "surge",
    "soar", "explode", "parabolic",
}
BEARISH_WORDS = {
    "bear", "bearish", "dump", "sell", "short", "crash", "correction",
    "bubble", "overvalued", "dead", "scam", "rug", "tank", "plunge",
    "collapse", "liquidated",
}

DEFAULT_SUBREDDITS = ["cryptocurrency", "bitcoin", "ethereum"]


class RedditProvider(DataProvider):
    """Reddit public JSON API for crypto sentiment (no auth required)."""

    def __init__(self) -> None:
        super().__init__(base_url=REDDIT_BASE, calls_per_minute=10)

    def _default_headers(self) -> dict[str, str]:
        headers = super()._default_headers()
        headers["User-Agent"] = "CryptoScope/0.1"
        return headers

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        """Not applicable for this provider."""
        return []

    async def fetch_subreddit_posts(
        self,
        subreddit: str = "cryptocurrency",
        sort: str = "hot",
        limit: int = 25,
    ) -> list[dict]:
        """Fetch recent posts from a subreddit."""
        try:
            data = await self._get(
                f"/r/{subreddit}/{sort}.json",
                params={"limit": str(limit), "raw_json": "1"},
            )
            posts = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                posts.append({
                    "title": post.get("title", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc", 0),
                    "subreddit": post.get("subreddit", subreddit),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                })
            return posts
        except Exception as e:
            logger.warning("Reddit fetch failed for r/%s: %s", subreddit, e)
            return []

    async def fetch_sentiment(
        self,
        subreddits: list[str] | None = None,
    ) -> dict:
        """Analyze sentiment across crypto subreddits.

        Returns dict with post_count, bullish_count, bearish_count, trending_topics.
        """
        subreddits = subreddits or DEFAULT_SUBREDDITS
        all_titles: list[str] = []
        total_posts = 0
        bullish = 0
        bearish = 0

        for sub in subreddits:
            posts = await self.fetch_subreddit_posts(sub, limit=25)
            total_posts += len(posts)
            for post in posts:
                title = post["title"].lower()
                all_titles.append(title)
                words = set(re.findall(r'\w+', title))
                if words & BULLISH_WORDS:
                    bullish += 1
                if words & BEARISH_WORDS:
                    bearish += 1

        # Extract trending topics (most common meaningful words)
        word_counts: Counter = Counter()
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "and",
            "but", "or", "nor", "not", "so", "yet", "both", "either",
            "neither", "each", "every", "all", "any", "few", "more",
            "most", "other", "some", "such", "no", "only", "own", "same",
            "than", "too", "very", "just", "about", "its", "it", "this",
            "that", "these", "those", "i", "my", "me", "we", "our", "you",
            "your", "he", "his", "she", "her", "they", "their", "what",
            "which", "who", "when", "where", "why", "how", "if", "up",
        }
        for title in all_titles:
            words = re.findall(r'\b[a-z]{3,}\b', title)
            for w in words:
                if w not in stop_words:
                    word_counts[w] += 1

        trending = [
            TrendingTopic(term=word, interest=float(count))
            for word, count in word_counts.most_common(10)
        ]

        return {
            "post_count": total_posts,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": total_posts - bullish - bearish,
            "trending_topics": trending,
        }
