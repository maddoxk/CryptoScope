"""Chart detail view panel for a selected coin."""

from __future__ import annotations

import os

from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cryptoscope.charting.engine import ChartConfig, Timeframe, render_candlestick_chart
from cryptoscope.charting.indicators import compute_all_indicators
from cryptoscope.models.price import OHLCV, OrderBook, Ticker
from cryptoscope.ui.panels import VIEW_CHART, build_footer, build_header, build_order_book_panel
import cryptoscope.ui.themes as _themes
from cryptoscope.utils.formatting import color_percent, format_large_number, format_price


def _term_size() -> tuple[int, int]:
    """Terminal width, height with fallback."""
    try:
        return os.get_terminal_size()
    except OSError:
        return 120, 40


class ChartView:
    """Manages the chart detail view state."""

    TIMEFRAMES = [Timeframe.H1, Timeframe.H4, Timeframe.D1, Timeframe.W1]

    CHART_KEYS: list[tuple[str, str]] = [
        ("Esc", "back"),
        ("←→", "timeframe"),
        ("+/-", "zoom"),
        ("s", "SMA"),
        ("e", "EMA"),
        ("b", "BB"),
        ("i", "RSI"),
        ("m", "MACD"),
        ("o", "book"),
        ("F7", "settings"),
    ]

    def __init__(self) -> None:
        self.coin_id: str = ""
        self.ticker: Ticker | None = None
        self.tickers: list[Ticker] = []  # for header ticker tape
        self.candles: list[OHLCV] = []
        self.timeframe_index: int = 2  # Default to 1d
        self.indicators: dict = {}
        self.chart_config = ChartConfig()
        self.zoom_level: int = 0
        self.last_update = None
        self.status: str = "OK"
        self.status_msg: str = ""
        self.provider: str = "coingecko"
        # Order book
        self.show_order_book: bool = False
        self.order_book: OrderBook | None = None
        self.binance_symbol: str = ""

    @property
    def timeframe(self) -> Timeframe:
        return self.TIMEFRAMES[self.timeframe_index]

    def _sidebar_width(self) -> int:
        """Responsive sidebar width."""
        term_w, _ = _term_size()
        return min(38, max(28, term_w // 4))

    def set_data(self, ticker: Ticker, candles: list[OHLCV]) -> None:
        """Update chart data and recompute indicators."""
        self.coin_id = ticker.id
        self.ticker = ticker
        self.candles = candles
        self.zoom_level = 0
        self._recompute_indicators()

    def cycle_timeframe(self, direction: int = 1) -> Timeframe:
        self.timeframe_index = (self.timeframe_index + direction) % len(self.TIMEFRAMES)
        return self.timeframe

    def zoom_in(self) -> None:
        total = len(self.candles)
        if self.zoom_level == 0:
            self.zoom_level = total
        self.zoom_level = max(10, self.zoom_level - max(5, total // 10))

    def zoom_out(self) -> None:
        total = len(self.candles)
        if self.zoom_level == 0:
            return
        self.zoom_level = min(total, self.zoom_level + max(5, total // 10))
        if self.zoom_level >= total:
            self.zoom_level = 0

    def toggle_indicator(self, name: str) -> None:
        cfg = self.chart_config
        if name == "rsi":
            cfg.show_rsi = not cfg.show_rsi
        elif name == "macd":
            cfg.show_macd = not cfg.show_macd
        elif name == "bollinger":
            cfg.show_bollinger = not cfg.show_bollinger
        elif name == "sma":
            cfg.show_sma = [] if cfg.show_sma else [20, 50]
        elif name == "ema":
            cfg.show_ema = [] if cfg.show_ema else [20, 50]

    def _recompute_indicators(self) -> None:
        if not self.candles:
            self.indicators = {}
            return
        self.indicators = compute_all_indicators(
            self.candles,
            sma_periods=self.chart_config.show_sma or [20, 50],
            ema_periods=self.chart_config.show_ema or [20, 50],
        )

    def _visible_candles(self) -> list[OHLCV]:
        if self.zoom_level == 0 or self.zoom_level >= len(self.candles):
            return self.candles
        return self.candles[-self.zoom_level:]

    def _chart_dimensions(self) -> tuple[int, int]:
        """Calculate width and height available for the plotext chart."""
        term_w, term_h = _term_size()
        sidebar_w = self._sidebar_width()

        # Chart panel gets: total width - sidebar width - order book (if visible)
        orderbook_w = 32 if (self.show_order_book and self.order_book) else 0
        chart_panel_w = term_w - sidebar_w - orderbook_w
        # Inside the panel: subtract border (2) + padding (2)
        chart_w = chart_panel_w - 4

        # Height: total - header(3) - breadcrumb(1) - footer(3) - panel border(2)
        chart_h = term_h - 3 - 1 - 3 - 2

        return max(40, chart_w), max(10, chart_h)

    def build(self) -> Layout:
        """Build the complete chart detail layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="breadcrumb", size=1),
            Layout(name="chart_body"),
            Layout(name="footer", size=3),
        )

        # Header — reuse shared ticker-tape header
        layout["header"].update(build_header(self.tickers, provider=self.provider))

        # Breadcrumb bar
        layout["breadcrumb"].update(self._build_breadcrumb())

        # Body: chart + (optional order book) + stats sidebar
        sidebar_w = self._sidebar_width()
        body = Layout()

        chart_text = self._render_chart()
        chart_panel = Panel(
            chart_text,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
            title=f"[bold grey70]{self.timeframe.label}[/bold grey70]",
        )

        if self.show_order_book and self.order_book:
            body.split_row(
                Layout(name="chart", minimum_size=40),
                Layout(name="orderbook", size=32),
                Layout(name="sidebar", size=sidebar_w),
            )
            body["orderbook"].update(build_order_book_panel(self.order_book))
        else:
            body.split_row(
                Layout(name="chart", minimum_size=40),
                Layout(name="sidebar", size=sidebar_w),
            )

        body["chart"].update(chart_panel)
        body["sidebar"].update(self._build_sidebar())
        layout["chart_body"].update(body)

        # Footer — shared
        layout["footer"].update(
            build_footer(
                active_view=VIEW_CHART,
                last_update=self.last_update,
                status=self.status,
                keybindings=self.CHART_KEYS,
                error_msg=self.status_msg,
            )
        )

        return layout

    def _build_breadcrumb(self) -> Text:
        """Breadcrumb: Watchlist > BTC Bitcoin  $xx,xxx  +x.x%  Timeframe: 1D"""
        t = self.ticker
        bc = Text()
        bc.append(" Watchlist", style="cornflower_blue")
        bc.append(" › ", style="grey42")
        if t:
            bc.append(f"{t.symbol}", style="bold bright_white")
            bc.append(f" {t.name}", style="grey62")
            bc.append(f"  {format_price(t.price_usd)}", style="bold bright_white")
            bc.append("  ")
            pct = t.change_24h
            sign = "+" if pct > 0 else ""
            style = "bold green" if pct > 0 else "bold red" if pct < 0 else "grey50"
            bc.append(f"{sign}{pct:.2f}%", style=style)
        else:
            bc.append("No coin selected", style="grey42")
        return bc

    def _render_chart(self) -> Text:
        """Render the price chart at the correct dimensions."""
        candles = self._visible_candles()
        if not candles:
            return Text("No candle data available.", style="grey42")

        # Slice indicators to match visible candles
        offset = len(self.candles) - len(candles)
        visible_indicators = {}
        for key, vals in self.indicators.items():
            visible_indicators[key] = vals[offset:]

        # Set chart dimensions to fit inside the panel
        chart_w, chart_h = self._chart_dimensions()
        self.chart_config.width = chart_w
        self.chart_config.height = chart_h

        title = f"{self.ticker.symbol if self.ticker else ''} {self.timeframe.label}"
        return render_candlestick_chart(
            candles, title=title, config=self.chart_config, indicators=visible_indicators
        )

    def _build_sidebar(self) -> Panel:
        """Single sidebar panel with Rule-separated sections."""
        content = Text()

        t = self.ticker
        if t:
            # --- Key Stats ---
            stats = [
                ("Rank", f"#{t.market_cap_rank}"),
                ("Mkt Cap", format_large_number(t.market_cap)),
                ("24h Vol", format_large_number(t.volume_24h)),
                ("1h", color_percent(t.change_1h)),
                ("24h", color_percent(t.change_24h)),
                ("7d", color_percent(t.change_7d)),
                ("ATH", format_price(t.ath)),
                ("ATL", format_price(t.atl)),
                ("Supply", f"{t.circulating_supply:,.0f}"),
            ]
            if t.max_supply:
                stats.append(("Max", f"{t.max_supply:,.0f}"))

            stats_table = Table(
                show_header=False,
                box=None,
                expand=True,
                pad_edge=True,
                padding=(0, 1),
            )
            stats_table.add_column("Stat", style="grey62", ratio=1)
            stats_table.add_column("Value", justify="right", style="bright_white", ratio=1)

            for label, val in stats:
                stats_table.add_row(label, Text.from_markup(val) if "[" in str(val) else val)

        # --- Indicator values ---
        ind_table = Table(
            show_header=False,
            box=None,
            expand=True,
            pad_edge=True,
            padding=(0, 1),
        )
        ind_table.add_column("Ind", style="grey62", ratio=1)
        ind_table.add_column("Val", justify="right", style="bright_white", ratio=1)

        def _last_valid(vals: list[float | None]) -> str:
            for v in reversed(vals):
                if v is not None:
                    return f"{v:,.2f}"
            return "---"

        ind = self.indicators

        for period in self.chart_config.show_sma:
            key = f"sma_{period}"
            if key in ind:
                ind_table.add_row(f"SMA({period})", _last_valid(ind[key]))

        for period in self.chart_config.show_ema:
            key = f"ema_{period}"
            if key in ind:
                ind_table.add_row(f"EMA({period})", _last_valid(ind[key]))

        if "rsi" in ind:
            rsi_val = _last_valid(ind["rsi"])
            status = ""
            try:
                rv = float(rsi_val.replace(",", ""))
                if rv >= 70:
                    status = " [red]OB[/red]"
                elif rv <= 30:
                    status = " [green]OS[/green]"
            except ValueError:
                pass
            ind_table.add_row("RSI(14)", Text.from_markup(f"{rsi_val}{status}"))

        if "macd_line" in ind:
            ind_table.add_row("MACD", _last_valid(ind["macd_line"]))
            ind_table.add_row("Signal", _last_valid(ind["macd_signal"]))
            ind_table.add_row("Hist", _last_valid(ind["macd_histogram"]))

        if "bb_upper" in ind:
            ind_table.add_row("BB ↑", _last_valid(ind["bb_upper"]))
            ind_table.add_row("BB ↓", _last_valid(ind["bb_lower"]))

        if "vwap" in ind:
            ind_table.add_row("VWAP", _last_valid(ind["vwap"]))

        # --- Toggles ---
        toggles = Text()
        cfg = self.chart_config
        for name, active in [
            ("SMA", bool(cfg.show_sma)),
            ("EMA", bool(cfg.show_ema)),
            ("BB", cfg.show_bollinger),
            ("RSI", cfg.show_rsi),
            ("MACD", cfg.show_macd),
        ]:
            icon = "●" if active else "○"
            style = "green" if active else "grey42"
            toggles.append(f" {icon} {name}", style=style)

        # Assemble sidebar with Rule separators
        sidebar = Layout()
        parts = []
        if t:
            parts.append(Layout(stats_table, name="stats", ratio=2))
            parts.append(Layout(Rule(style="grey27"), name="rule1", size=1))
        parts.append(Layout(ind_table, name="indicators", ratio=2))
        parts.append(Layout(Rule(style="grey27"), name="rule2", size=1))
        parts.append(Layout(toggles, name="toggles", size=1))

        sidebar.split_column(*parts)

        return Panel(
            sidebar,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
            title="[bold grey70]Details[/bold grey70]",
        )
