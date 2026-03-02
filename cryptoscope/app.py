"""Main CryptoScope application — orchestrates data fetching and UI rendering."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from enum import Enum, auto

from rich.console import Console
from rich.live import Live

from cryptoscope.config import ensure_config
from cryptoscope.data.coingecko import CoinGeckoProvider
from cryptoscope.data.cryptopanic import CryptoPanicProvider
from cryptoscope.data.fear_greed import FearGreedProvider
from cryptoscope.data.lunarcrush import LunarCrushProvider
from cryptoscope.data.reddit import RedditProvider
from cryptoscope.data.trends import GoogleTrendsProvider
from cryptoscope.db import Database
from cryptoscope.ui.chart_view import ChartView
from cryptoscope.ui.input import TerminalInput
from cryptoscope.ui.layout import TerminalLayout
from cryptoscope.ui.sentiment_view import SentimentView
from cryptoscope.ui.themes import CRYPTOSCOPE_THEME

logger = logging.getLogger(__name__)


class ViewMode(Enum):
    WATCHLIST = auto()
    CHART = auto()
    SENTIMENT = auto()


class CryptoScopeApp:
    """Main application controller."""

    def __init__(self) -> None:
        self.config = ensure_config()
        self.console = Console(theme=CRYPTOSCOPE_THEME)
        self.layout = TerminalLayout()
        self.chart_view = ChartView()
        self.sentiment_view = SentimentView()
        self.view_mode = ViewMode.WATCHLIST
        self._running = False
        self._needs_render = asyncio.Event()
        self._selected_row = 0
        self._input = TerminalInput()

        # Database
        self.db = Database()

        # Providers
        api_keys = self.config["api_keys"]
        currency = self.config["general"].get("currency", "usd")
        self.coingecko = CoinGeckoProvider(api_key=api_keys.get("coingecko", ""), currency=currency)
        self.fear_greed = FearGreedProvider()
        self.cryptopanic = CryptoPanicProvider(api_key=api_keys.get("cryptopanic", ""))
        self.lunarcrush = LunarCrushProvider(api_key=api_keys.get("lunarcrush", ""))
        self.reddit = RedditProvider()
        self.trends = GoogleTrendsProvider()

    # --- Data fetching ---

    async def _fetch_watchlist(self) -> None:
        """Fetch watchlist data from CoinGecko."""
        try:
            coin_ids = self.config["watchlist"]["coins"]
            tickers = await self.coingecko.fetch_tickers(coin_ids)
            self.layout.update_tickers(tickers)
            self.layout.status = "OK"
            # Share tickers with other views for header ticker tape
            self.chart_view.tickers = tickers
            self.sentiment_view.tickers = tickers
            for t in tickers:
                await self.db.snapshot_save(
                    t.id, t.price_usd, t.market_cap, t.volume_24h, t.change_24h
                )
            # Populate sparkline price history
            history: dict[str, list[float]] = {}
            for t in tickers:
                history[t.id] = await self.db.snapshot_get_recent_prices(t.id)
            self.layout.price_history = history
        except Exception as e:
            logger.error("Failed to fetch watchlist: %s", e)
            self.layout.status = "ERROR"

    async def _fetch_chart_data(self, coin_id: str) -> None:
        """Fetch OHLCV data for the chart view."""
        try:
            tf = self.chart_view.timeframe
            candles = await self.coingecko.fetch_ohlcv(coin_id, days=tf.coingecko_days)
            ticker = next((t for t in self.layout.tickers if t.id == coin_id), None)
            if ticker and candles:
                self.chart_view.set_data(ticker, candles)
                self.chart_view.last_update = self.layout.last_update
        except Exception as e:
            logger.error("Failed to fetch chart data for %s: %s", coin_id, e)

    async def _fetch_sentiment_data(self) -> None:
        """Fetch all sentiment data sources concurrently."""
        sv = self.sentiment_view

        async def _fetch_fear_greed():
            try:
                current = await self.fear_greed.fetch_current()
                if current:
                    sv.fear_greed_current = current
                history = await self.fear_greed.fetch_history(days=30)
                sv.fear_greed_history = history
            except Exception as e:
                logger.warning("Fear & Greed fetch failed: %s", e)

        async def _fetch_news():
            try:
                symbols = [t.symbol for t in self.layout.tickers[:5]]
                currencies = ",".join(symbols) if symbols else ""
                sv.news_items = await self.cryptopanic.fetch_news(currencies=currencies)
            except Exception as e:
                logger.warning("News fetch failed: %s", e)

        async def _fetch_social():
            try:
                symbols = [t.symbol for t in self.layout.tickers[:5]]
                if symbols:
                    sv.social_metrics = await self.lunarcrush.fetch_social_metrics(symbols)
            except Exception as e:
                logger.warning("Social metrics fetch failed: %s", e)

        async def _fetch_reddit():
            try:
                sv.reddit_summary = await self.reddit.fetch_sentiment()
                reddit_topics = sv.reddit_summary.get("trending_topics", [])
                if reddit_topics and not sv.trending_topics:
                    sv.trending_topics = reddit_topics
            except Exception as e:
                logger.warning("Reddit fetch failed: %s", e)

        async def _fetch_trends():
            try:
                if self.trends.available:
                    sv.trending_topics = await self.trends.fetch_interest()
            except Exception as e:
                logger.warning("Google Trends fetch failed: %s", e)

        await asyncio.gather(
            _fetch_fear_greed(),
            _fetch_news(),
            _fetch_social(),
            _fetch_reddit(),
            _fetch_trends(),
            return_exceptions=True,
        )
        sv.last_update = datetime.now()

    # --- Rendering ---

    def _current_renderable(self):
        """Get the current view's renderable."""
        if self.view_mode == ViewMode.CHART:
            return self.chart_view.build()
        elif self.view_mode == ViewMode.SENTIMENT:
            return self.sentiment_view.build()
        return self.layout.build(selected_row=self._selected_row)

    def _request_render(self) -> None:
        """Signal that the display needs updating."""
        self._needs_render.set()

    # --- Main loops ---

    async def _render_loop(self, live: Live) -> None:
        """Single render loop — the ONLY place that calls live.update().

        This prevents race conditions between refresh and key handling.
        A small debounce after each render avoids flicker from rapid key
        presses.
        """
        while self._running:
            live.update(self._current_renderable())
            live.refresh()
            self._needs_render.clear()
            # Small debounce — don't re-render faster than ~30fps
            await asyncio.sleep(0.033)
            # Then wait for next render request or 1s ceiling (header clock)
            try:
                await asyncio.wait_for(self._needs_render.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    async def _data_loop(self) -> None:
        """Periodically fetch fresh data for the active view."""
        interval = self.config["general"].get("refresh_interval", 10)
        while self._running:
            try:
                if self.view_mode == ViewMode.WATCHLIST:
                    await self._fetch_watchlist()
                elif self.view_mode == ViewMode.SENTIMENT:
                    await self._fetch_sentiment_data()
                self._request_render()
            except Exception as e:
                logger.error("Data loop error: %s", e)
            await asyncio.sleep(interval)

    async def _input_loop(self) -> None:
        """Read keys and dispatch to handlers."""
        while self._running:
            try:
                key = await self._input.read_key()
                await self._handle_key(key)
            except Exception:
                await asyncio.sleep(0.1)

    # --- Key handling ---

    async def _handle_key(self, key: str) -> None:
        """Process a keypress based on current view."""
        if key in ("q", "Q"):
            self._running = False
            return

        # Global tab switching
        if key == "F1":
            if self.view_mode != ViewMode.WATCHLIST:
                self.view_mode = ViewMode.WATCHLIST
                self._request_render()
            return
        if key == "F2":
            if self.view_mode != ViewMode.SENTIMENT:
                self.view_mode = ViewMode.SENTIMENT
                # Kick off a fetch in the background
                asyncio.create_task(self._fetch_and_render_sentiment())
            return

        if self.view_mode == ViewMode.WATCHLIST:
            await self._handle_watchlist_key(key)
        elif self.view_mode == ViewMode.CHART:
            await self._handle_chart_key(key)
        elif self.view_mode == ViewMode.SENTIMENT:
            await self._handle_sentiment_key(key)

    async def _fetch_and_render_sentiment(self) -> None:
        """Fetch sentiment data then trigger a render."""
        await self._fetch_sentiment_data()
        self._request_render()

    async def _handle_watchlist_key(self, key: str) -> None:
        tickers = self.layout.tickers
        if key in ("r", "R"):
            await self._fetch_watchlist()
            self._request_render()
        elif key == "UP":
            self._selected_row = max(0, self._selected_row - 1)
            self._request_render()
        elif key == "DOWN":
            self._selected_row = min(len(tickers) - 1, self._selected_row + 1)
            self._request_render()
        elif key == "ENTER":
            if tickers and 0 <= self._selected_row < len(tickers):
                await self._fetch_chart_data(tickers[self._selected_row].id)
                self.view_mode = ViewMode.CHART
                self._request_render()
        elif key == "2":
            self.view_mode = ViewMode.SENTIMENT
            asyncio.create_task(self._fetch_and_render_sentiment())

    async def _handle_chart_key(self, key: str) -> None:
        cv = self.chart_view
        needs_data = False

        if key == "ESCAPE" or key == "BACKSPACE":
            self.view_mode = ViewMode.WATCHLIST
            self._request_render()
            return
        elif key == "LEFT":
            cv.cycle_timeframe(-1)
            needs_data = True
        elif key == "RIGHT":
            cv.cycle_timeframe(1)
            needs_data = True
        elif key == "+":
            cv.zoom_in()
        elif key == "-":
            cv.zoom_out()
        elif key in ("s", "S"):
            cv.toggle_indicator("sma")
        elif key in ("e", "E"):
            cv.toggle_indicator("ema")
        elif key in ("b", "B"):
            cv.toggle_indicator("bollinger")
        elif key in ("i", "I"):
            cv.toggle_indicator("rsi")
        elif key in ("m", "M"):
            cv.toggle_indicator("macd")

        if needs_data and cv.coin_id:
            await self._fetch_chart_data(cv.coin_id)

        self._request_render()

    async def _handle_sentiment_key(self, key: str) -> None:
        if key == "ESCAPE" or key == "BACKSPACE":
            self.view_mode = ViewMode.WATCHLIST
            self._request_render()
        elif key in ("r", "R"):
            await self._fetch_sentiment_data()
            self._request_render()
        elif key == "UP":
            self.sentiment_view.scroll_news(-1)
            self._request_render()
        elif key == "DOWN":
            self.sentiment_view.scroll_news(1)
            self._request_render()
        elif key == "1":
            self.view_mode = ViewMode.WATCHLIST
            self._request_render()

    # --- Lifecycle ---

    async def run(self) -> None:
        """Run the application."""
        self._running = True

        await self.db.connect()
        await self._fetch_watchlist()

        self._input.start()
        try:
            with Live(
                self._current_renderable(),
                console=self.console,
                auto_refresh=False,
                screen=True,
            ) as live:
                try:
                    render_task = asyncio.create_task(self._render_loop(live))
                    data_task = asyncio.create_task(self._data_loop())
                    input_task = asyncio.create_task(self._input_loop())

                    done, pending = await asyncio.wait(
                        [render_task, data_task, input_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                finally:
                    await self.coingecko.close()
                    await self.fear_greed.close()
                    await self.cryptopanic.close()
                    await self.lunarcrush.close()
                    await self.reddit.close()
                    await self.db.close()
        finally:
            self._input.stop()

        self.console.print("[dim]CryptoScope terminated.[/dim]")
