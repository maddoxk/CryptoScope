"""Sentiment dashboard view — Fear/Greed, news, social metrics, trends."""

from __future__ import annotations

from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cryptoscope.models.sentiment import (
    FearGreedEntry,
    NewsItem,
    SocialMetrics,
    TrendingTopic,
)
from cryptoscope.ui.panels import VIEW_SENTIMENT, build_footer, build_header
import cryptoscope.ui.themes as _themes


class SentimentView:
    """Manages the sentiment dashboard state and rendering."""

    SENTIMENT_KEYS: list[tuple[str, str]] = [
        ("Esc", "back"),
        ("↑↓", "scroll"),
        ("r", "refresh"),
        ("F7", "settings"),
        ("q", "quit"),
    ]

    def __init__(self) -> None:
        self.fear_greed_current: FearGreedEntry | None = None
        self.fear_greed_history: list[FearGreedEntry] = []
        self.news_items: list[NewsItem] = []
        self.social_metrics: list[SocialMetrics] = []
        self.trending_topics: list[TrendingTopic] = []
        self.reddit_summary: dict = {}
        self.news_scroll_offset: int = 0
        self.tickers = []  # for header ticker tape
        self.last_update = None
        self.status: str = "OK"
        self.status_msg: str = ""

    def scroll_news(self, direction: int) -> None:
        """Scroll the news feed up or down."""
        max_offset = max(0, len(self.news_items) - 15)
        self.news_scroll_offset = max(0, min(max_offset, self.news_scroll_offset + direction))

    def build(self) -> Layout:
        """Build the complete sentiment dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        # Shared header
        layout["header"].update(build_header(self.tickers))

        # Body: 3-column layout
        body = Layout()
        body.split_row(
            Layout(name="left", size=24),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=3),
        )

        # Left: Fear/Greed + Trending
        left = Layout()
        left.split_column(
            Layout(name="fear_greed", size=11),
            Layout(name="trending"),
        )
        left["fear_greed"].update(self._build_fear_greed_panel())
        left["trending"].update(self._build_trending_panel())
        body["left"].update(left)

        # Center: Social Buzz + Reddit
        body["center"].update(self._build_social_panel())

        # Right: News feed
        body["right"].update(self._build_news_panel())

        layout["body"].update(body)

        # Shared footer
        layout["footer"].update(
            build_footer(
                active_view=VIEW_SENTIMENT,
                last_update=self.last_update,
                status=self.status,
                keybindings=self.SENTIMENT_KEYS,
                error_msg=self.status_msg,
            )
        )

        return layout

    def _build_fear_greed_panel(self) -> Panel:
        """Compact Fear & Greed — big number + mini gauge + 7d history."""
        fg = self.fear_greed_current

        if not fg:
            return Panel(
                Text("Unavailable", style="grey42", justify="center"),
                title="[bold grey70]Fear & Greed[/bold grey70]",
                box=_themes.BOX_DEFAULT,
                border_style=_themes.BORDER_DIM,
            )

        content = Text(justify="center")

        # Big centered number
        content.append(f"\n{fg.value}", style=f"bold {fg.color}")
        content.append(f"\n{fg.classification}", style=f"{fg.color}")

        # Mini gauge bar (16 chars)
        content.append("\n")
        gauge_width = 16
        filled = int((fg.value / 100) * gauge_width)
        for i in range(gauge_width):
            if i < gauge_width * 0.25:
                color = "red"
            elif i < gauge_width * 0.5:
                color = "orange1"
            elif i < gauge_width * 0.75:
                color = "green_yellow"
            else:
                color = "green"
            content.append("█" if i < filled else "░", style=color if i < filled else "grey19")

        # 7d history sparkline
        if self.fear_greed_history:
            content.append("\n7d: ", style="grey62")
            recent = self.fear_greed_history[:7]
            for entry in reversed(recent):
                content.append("█", style=entry.color)
            content.append(
                f" {recent[0].value}→{recent[-1].value}" if len(recent) > 1 else "",
                style="grey42",
            )
        content.append("\n")

        return Panel(
            content,
            title="[bold grey70]Fear & Greed[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )

    def _build_social_panel(self) -> Panel:
        """Social metrics table with Reddit stats below a Rule."""
        table = Table(
            show_header=True,
            header_style="bold grey70",
            box=None,
            expand=True,
            pad_edge=True,
            row_styles=["", "on grey7"],
        )
        table.add_column("Coin", min_width=5)
        table.add_column("Mentions", justify="right", min_width=7)
        table.add_column("Engage", justify="right", min_width=7)
        table.add_column("Bull%", justify="right", min_width=6)
        table.add_column("Galaxy", justify="right", min_width=5)

        if not self.social_metrics:
            table.add_row("---", "---", "---", "---", "---")
        else:
            for m in self.social_metrics:
                bull_style = (
                    "green" if m.sentiment_bullish_pct > 60
                    else "red" if m.sentiment_bullish_pct < 40
                    else "grey50"
                )
                galaxy_style = (
                    "green" if m.galaxy_score >= 70
                    else "red" if m.galaxy_score < 40
                    else "grey50"
                )
                table.add_row(
                    Text(m.symbol, style="bold bright_white"),
                    f"{m.mentions_24h:,}",
                    f"{m.engagement_score:,.0f}",
                    Text(f"{m.sentiment_bullish_pct:.0f}%", style=bull_style),
                    Text(f"{m.galaxy_score:.0f}", style=galaxy_style),
                )

        # Reddit summary below Rule
        reddit_text = Text()
        if self.reddit_summary:
            rs = self.reddit_summary
            reddit_text.append(f" Reddit  ", style="grey62")
            reddit_text.append(f"{rs.get('post_count', 0)} posts  ", style="bright_white")
            reddit_text.append(f"▲{rs.get('bullish_count', 0)} ", style="green")
            reddit_text.append(f"▼{rs.get('bearish_count', 0)} ", style="red")
            reddit_text.append(f"—{rs.get('neutral_count', 0)}", style="grey50")

        inner = Layout()
        inner.split_column(
            Layout(table, name="social_table", ratio=3),
            Layout(Rule(style="grey27"), name="rule", size=1),
            Layout(reddit_text, name="reddit", size=2),
        )

        return Panel(
            inner,
            title="[bold grey70]Social Buzz[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )

    def _build_trending_panel(self) -> Panel:
        """Trending topics — top 6, compact."""
        topics = self.trending_topics or (
            self.reddit_summary.get("trending_topics", []) if self.reddit_summary else []
        )

        if not topics:
            return Panel(
                Text("No trending data", style="grey42", justify="center"),
                title="[bold grey70]Trending[/bold grey70]",
                box=_themes.BOX_DEFAULT,
                border_style=_themes.BORDER_DIM,
            )

        text = Text()
        for i, topic in enumerate(topics[:6]):
            style = "bold orange1" if topic.is_spike else "bright_white"
            text.append(f"\n {i+1}. ", style="grey50")
            text.append(topic.term, style=style)
            if topic.change_pct:
                pct_style = "green" if topic.change_pct > 0 else "red"
                sign = "+" if topic.change_pct > 0 else ""
                text.append(f" {sign}{topic.change_pct:.0f}%", style=pct_style)

        return Panel(
            text,
            title="[bold grey70]Trending[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )

    def _build_news_panel(self) -> Panel:
        """Scrollable news feed with sentiment arrows and coin tags."""
        if not self.news_items:
            return Panel(
                Text(
                    "No news available.\nConfigure CryptoPanic API key.",
                    style="grey42",
                    justify="center",
                ),
                title="[bold grey70]News Feed[/bold grey70]",
                box=_themes.BOX_DEFAULT,
                border_style=_themes.BORDER_DIM,
            )

        text = Text()
        visible = self.news_items[self.news_scroll_offset:self.news_scroll_offset + 15]

        for item in visible:
            # Sentiment arrow
            arrows = {"bullish": ("▲", "green"), "bearish": ("▼", "red"), "neutral": ("●", "grey50")}
            arrow, arrow_style = arrows.get(item.sentiment, ("●", "grey50"))
            text.append(f"\n {arrow} ", style=arrow_style)

            # Title
            title = item.title
            if len(title) > 65:
                title = title[:62] + "..."
            text.append(title, style="bright_white")

            # Meta line: coin tags + source + time
            text.append("\n   ")
            if item.coins:
                for coin in item.coins[:3]:
                    text.append(f" {coin} ", style="bold cornflower_blue")
                    text.append(" ")
            text.append(f"{item.source}", style="grey50")
            text.append(f" · {item.time_ago}", style="grey42")

        # Scroll indicator
        total = len(self.news_items)
        if total > 15:
            start = self.news_scroll_offset + 1
            end = min(self.news_scroll_offset + 15, total)
            text.append(f"\n\n {start}-{end} of {total}  ↑↓ scroll", style="grey42")

        return Panel(
            text,
            title="[bold grey70]News Feed[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )
