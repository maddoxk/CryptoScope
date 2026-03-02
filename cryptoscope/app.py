"""Main CryptoScope application — orchestrates data fetching and UI rendering."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime
from enum import Enum, auto

import httpx

from rich.console import Console
from rich.live import Live

from cryptoscope.config import ensure_config, save_config
from cryptoscope.data.binance import BinanceProvider
from cryptoscope.data.coingecko import CoinGeckoProvider
from cryptoscope.data.symbol_map import coingecko_to_binance
from cryptoscope.data.cryptopanic import CryptoPanicProvider
from cryptoscope.data.fear_greed import FearGreedProvider
from cryptoscope.data.lunarcrush import LunarCrushProvider
from cryptoscope.data.reddit import RedditProvider
from cryptoscope.data.trends import GoogleTrendsProvider
from cryptoscope.db import Database
from cryptoscope.ui.chart_view import ChartView
from cryptoscope.ui.input import TerminalInput
from cryptoscope.ui.layout import TerminalLayout
from cryptoscope.ui.pair_finder import PairFinderView
from cryptoscope.ui.sentiment_view import SentimentView
from cryptoscope.ui.settings_view import SettingsView
from cryptoscope.ui.themes import CRYPTOSCOPE_THEME, apply_theme

logger = logging.getLogger(__name__)


class ViewMode(Enum):
    WATCHLIST = auto()
    CHART = auto()
    SENTIMENT = auto()
    PAIRS = auto()
    SETTINGS = auto()


class CryptoScopeApp:
    """Main application controller."""

    def __init__(self) -> None:
        self.config = ensure_config()
        # Apply saved theme
        theme_name = self.config["general"].get("theme", "default")
        theme = apply_theme(theme_name)
        self.console = Console(theme=theme)
        self.layout = TerminalLayout()
        self.chart_view = ChartView()
        self.sentiment_view = SentimentView()
        self.pair_finder = PairFinderView()
        self.settings_view = SettingsView()
        self.settings_view.on_theme_change = self._apply_theme
        self.view_mode = ViewMode.WATCHLIST
        self._previous_view = ViewMode.WATCHLIST
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
        self.binance = BinanceProvider()

    # --- Error classification ---

    @staticmethod
    def _classify_error(e: Exception, provider: str = "") -> str:
        """Convert an exception into a short, user-readable status message."""
        src = f"{provider}: " if provider else ""
        if isinstance(e, httpx.HTTPStatusError):
            code = e.response.status_code
            if code == 429:
                return f"{src}429 Rate limited — slow down or add API key (F7)"
            elif code == 401:
                return f"{src}401 Unauthorized — check API key in Settings (F7)"
            elif code == 403:
                return f"{src}403 Forbidden — API key missing or invalid (F7)"
            elif code == 404:
                return f"{src}404 Endpoint not found — API may have changed"
            elif code == 422:
                return f"{src}422 Invalid request params"
            elif code in (500, 502, 503, 504):
                return f"{src}{code} Server error — will retry"
            else:
                return f"{src}HTTP {code} error"
        elif isinstance(e, httpx.ConnectTimeout):
            return f"{src}Connection timed out — check internet"
        elif isinstance(e, httpx.ReadTimeout):
            return f"{src}Read timed out — server too slow"
        elif isinstance(e, httpx.ConnectError):
            return f"{src}Cannot connect — check internet connection"
        elif isinstance(e, httpx.NetworkError):
            return f"{src}Network error — check internet connection"
        elif isinstance(e, httpx.DecodingError):
            return f"{src}Invalid response — unexpected API format"
        elif isinstance(e, asyncio.TimeoutError):
            return f"{src}Request timed out"
        else:
            # Truncate long generic messages
            msg = str(e)
            if len(msg) > 60:
                msg = msg[:57] + "…"
            return f"{src}{msg}" if msg else f"{src}Unexpected error"

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
            self.layout.status_msg = ""
        except Exception as e:
            logger.error("Failed to fetch watchlist: %s", e)
            self.layout.status = "ERROR"
            self.layout.status_msg = self._classify_error(e, "CoinGecko")

    async def _fetch_chart_data(self, coin_id: str) -> None:
        """Fetch OHLCV data for the chart view.

        Prefers Binance klines (which include real volume data) and falls
        back to CoinGecko OHLCV when no Binance symbol mapping exists.
        """
        try:
            tf = self.chart_view.timeframe
            ticker = next((t for t in self.layout.tickers if t.id == coin_id), None)
            if not ticker:
                return

            binance_symbol = coingecko_to_binance(coin_id, ticker.symbol)
            candles = None

            if binance_symbol:
                try:
                    candles = await self.binance.fetch_klines(
                        binance_symbol,
                        interval=tf.binance_interval,
                        limit=200,
                    )
                    self.chart_view.binance_symbol = binance_symbol
                except Exception as e:
                    logger.warning("Binance klines failed for %s, falling back to CoinGecko: %s", binance_symbol, e)

            if not candles:
                candles = await self.coingecko.fetch_ohlcv(coin_id, days=tf.coingecko_days)
                self.chart_view.binance_symbol = binance_symbol or ""

            if candles:
                self.chart_view.set_data(ticker, candles)
                self.chart_view.last_update = self.layout.last_update
                self.chart_view.status = "OK"
                self.chart_view.status_msg = ""
        except Exception as e:
            logger.error("Failed to fetch chart data for %s: %s", coin_id, e)
            self.chart_view.status = "ERROR"
            self.chart_view.status_msg = self._classify_error(e, "Chart")

    async def _fetch_sentiment_data(self) -> None:
        """Fetch all sentiment data sources concurrently."""
        sv = self.sentiment_view

        errors: list[str] = []

        async def _fetch_fear_greed():
            try:
                current = await self.fear_greed.fetch_current()
                if current:
                    sv.fear_greed_current = current
                history = await self.fear_greed.fetch_history(days=30)
                sv.fear_greed_history = history
            except Exception as e:
                logger.warning("Fear & Greed fetch failed: %s", e)
                errors.append(self._classify_error(e, "Fear/Greed"))

        async def _fetch_news():
            try:
                symbols = [t.symbol for t in self.layout.tickers[:5]]
                currencies = ",".join(symbols) if symbols else ""
                sv.news_items = await self.cryptopanic.fetch_news(currencies=currencies)
            except Exception as e:
                logger.warning("News fetch failed: %s", e)
                errors.append(self._classify_error(e, "CryptoPanic"))

        async def _fetch_social():
            try:
                symbols = [t.symbol for t in self.layout.tickers[:5]]
                if symbols:
                    sv.social_metrics = await self.lunarcrush.fetch_social_metrics(symbols)
            except Exception as e:
                logger.warning("Social metrics fetch failed: %s", e)
                errors.append(self._classify_error(e, "LunarCrush"))

        async def _fetch_reddit():
            try:
                sv.reddit_summary = await self.reddit.fetch_sentiment()
                reddit_topics = sv.reddit_summary.get("trending_topics", [])
                if reddit_topics and not sv.trending_topics:
                    sv.trending_topics = reddit_topics
            except Exception as e:
                logger.warning("Reddit fetch failed: %s", e)
                errors.append(self._classify_error(e, "Reddit"))

        async def _fetch_trends():
            try:
                if self.trends.available:
                    sv.trending_topics = await self.trends.fetch_interest()
            except Exception as e:
                logger.warning("Google Trends fetch failed: %s", e)
                errors.append(self._classify_error(e, "Trends"))

        await asyncio.gather(
            _fetch_fear_greed(),
            _fetch_news(),
            _fetch_social(),
            _fetch_reddit(),
            _fetch_trends(),
            return_exceptions=True,
        )
        sv.last_update = datetime.now()
        if errors:
            sv.status = "ERROR"
            sv.status_msg = errors[0]  # show the first (most prominent) error
        else:
            sv.status = "OK"
            sv.status_msg = ""

    # --- Theme ---

    def _apply_theme(self, theme_name: str) -> None:
        """Live-apply a new theme. Updates console and module-level constants."""
        new_theme = apply_theme(theme_name)
        self.console.push_theme(new_theme)

    # --- Rendering ---

    def _current_renderable(self):
        """Get the current view's renderable."""
        if self.view_mode == ViewMode.CHART:
            return self.chart_view.build()
        elif self.view_mode == ViewMode.SENTIMENT:
            return self.sentiment_view.build()
        elif self.view_mode == ViewMode.PAIRS:
            return self.pair_finder.build()
        elif self.view_mode == ViewMode.SETTINGS:
            return self.settings_view.build()
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
                if self.view_mode in (ViewMode.SETTINGS, ViewMode.PAIRS):
                    pass  # Skip data fetch while in settings or pair finder
                elif self.view_mode == ViewMode.WATCHLIST:
                    await self._fetch_watchlist()
                elif self.view_mode == ViewMode.CHART:
                    # Refresh order book if visible
                    cv = self.chart_view
                    if cv.show_order_book and cv.binance_symbol:
                        try:
                            cv.order_book = await self.binance.fetch_order_book(cv.binance_symbol)
                            cv.status = "OK"
                            cv.status_msg = ""
                        except Exception as e:
                            logger.warning("Order book refresh failed: %s", e)
                            cv.status = "ERROR"
                            cv.status_msg = self._classify_error(e, "Binance")
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
        # In settings edit mode, route all keys to settings (including q)
        if self.view_mode == ViewMode.SETTINGS and self.settings_view.editing:
            await self._handle_settings_key(key)
            return

        # In pair finder search mode, route all keys (including q) to pair finder
        if self.view_mode == ViewMode.PAIRS and self.pair_finder.searching:
            await self._handle_pairs_key(key)
            return

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
                asyncio.create_task(self._fetch_and_render_sentiment())
            return
        if key == "F3":
            if self.view_mode != ViewMode.PAIRS:
                self._previous_view = self.view_mode
                self.view_mode = ViewMode.PAIRS
                self.pair_finder.tickers = self.layout.tickers
                self.pair_finder.watchlist_coins = list(
                    self.config["watchlist"].get("coins", [])
                )
                asyncio.create_task(self._fetch_and_render_pairs())
            return
        if key == "F7":
            if self.view_mode != ViewMode.SETTINGS:
                self._previous_view = self.view_mode
                self.view_mode = ViewMode.SETTINGS
                self.settings_view.load(self.config)
                self.settings_view.tickers = self.layout.tickers
                self.settings_view.last_update = self.layout.last_update
                self._request_render()
            return

        if self.view_mode == ViewMode.WATCHLIST:
            await self._handle_watchlist_key(key)
        elif self.view_mode == ViewMode.CHART:
            await self._handle_chart_key(key)
        elif self.view_mode == ViewMode.SENTIMENT:
            await self._handle_sentiment_key(key)
        elif self.view_mode == ViewMode.PAIRS:
            await self._handle_pairs_key(key)
        elif self.view_mode == ViewMode.SETTINGS:
            await self._handle_settings_key(key)

    async def _fetch_and_render_sentiment(self) -> None:
        """Fetch sentiment data then trigger a render."""
        await self._fetch_sentiment_data()
        self._request_render()

    async def _fetch_and_render_pairs(self) -> None:
        """Ensure coin list is loaded, then fetch first page."""
        await self._fetch_coin_list()
        await self._fetch_pairs_page()
        self._request_render()

    async def _fetch_coin_list(self) -> None:
        """Fetch the full CoinGecko coin index, using 24h DB cache."""
        pf = self.pair_finder
        try:
            cached = await self.db.cache_get("coingecko_coin_list")
            if cached:
                pf.coin_list = cached
            else:
                coin_list = await self.coingecko.fetch_coin_list()
                pf.coin_list = coin_list
                await self.db.cache_set("coingecko_coin_list", coin_list, ttl_seconds=86400)

            total = len(pf.coin_list)
            pf.total_coins = total
            pf.total_pages = max(1, (total + pf.per_page - 1) // pf.per_page)
            pf.status_msg = ""
        except Exception as e:
            logger.error("Failed to fetch coin list: %s", e)
            pf.status = "ERROR"
            pf.status_msg = self._classify_error(e, "CoinGecko")

    async def _fetch_pairs_page(self) -> None:
        """Fetch market data for the current page (browse or search mode)."""
        pf = self.pair_finder
        try:
            if pf.search_query and pf.search_results:
                # Search mode: get market data for matching IDs
                result_ids = [c["id"] for c in pf.search_results]
                # Paginate the search results client-side
                start = (pf.current_page - 1) * pf.per_page
                page_ids = result_ids[start:start + pf.per_page]
                tickers = await self.coingecko.fetch_coins_by_ids(page_ids)
                pf.page_tickers = tickers
                total = len(result_ids)
                pf.total_coins = total
                pf.total_pages = max(1, (total + pf.per_page - 1) // pf.per_page)
            else:
                # Browse mode: paginated market data by market cap
                tickers = await self.coingecko.fetch_market_page(
                    page=pf.current_page, per_page=pf.per_page
                )
                if tickers:
                    pf.page_tickers = tickers
                    # Update total_pages as a floor — we know we can reach this page
                    pf.total_pages = max(pf.total_pages, pf.current_page)
                else:
                    # Past the real end — roll back
                    pf.current_page = max(1, pf.current_page - 1)
                    pf.total_pages = pf.current_page

            pf.selected_row = min(pf.selected_row, max(0, len(pf.page_tickers) - 1))
            pf.status = "OK"
            pf.status_msg = ""
            self._request_render()
        except Exception as e:
            logger.error("Failed to fetch pairs page: %s", e)
            pf.status = "ERROR"
            pf.status_msg = self._classify_error(e, "CoinGecko")
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
        elif key in ("o", "O"):
            cv.show_order_book = not cv.show_order_book
            if cv.show_order_book and cv.binance_symbol:
                try:
                    cv.order_book = await self.binance.fetch_order_book(cv.binance_symbol)
                    cv.status = "OK"
                    cv.status_msg = ""
                except Exception as e:
                    logger.warning("Order book fetch failed: %s", e)
                    cv.status = "ERROR"
                    cv.status_msg = self._classify_error(e, "Binance")

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

    async def _handle_pairs_key(self, key: str) -> None:
        pf = self.pair_finder
        action = pf.handle_key(key)
        if action == "exit":
            self.view_mode = self._previous_view
        elif action == "fetch_page":
            asyncio.create_task(self._fetch_pairs_page())
        elif action == "fetch_search":
            asyncio.create_task(self._fetch_pairs_page())
        elif action == "add":
            coin = pf.selected_coin
            if coin:
                watchlist = self.config["watchlist"].get("coins", [])
                if coin.id not in watchlist:
                    watchlist.append(coin.id)
                    self.config["watchlist"]["coins"] = watchlist
                    save_config(self.config)
                    pf.watchlist_coins = list(watchlist)
                    pf.flash(f"Added {coin.symbol} to watchlist")
                else:
                    pf.flash(f"{coin.symbol} already in watchlist")
        elif action == "remove":
            coin = pf.selected_coin
            if coin:
                watchlist = self.config["watchlist"].get("coins", [])
                if coin.id in watchlist:
                    watchlist.remove(coin.id)
                    self.config["watchlist"]["coins"] = watchlist
                    save_config(self.config)
                    pf.watchlist_coins = list(watchlist)
                    pf.flash(f"Removed {coin.symbol} from watchlist")
                else:
                    pf.flash(f"{coin.symbol} not in watchlist")
        self._request_render()

    async def _handle_settings_key(self, key: str) -> None:
        result = self.settings_view.handle_key(key)
        if result == "exit":
            # Apply config changes back to the running app
            self.config = self.settings_view.config
            self.view_mode = self._previous_view
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
                    await self.binance.close()
                    await self.reddit.close()
                    await self.db.close()
        finally:
            self._input.stop()

        self.console.print("[dim]CryptoScope terminated.[/dim]")
