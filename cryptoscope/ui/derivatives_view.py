"""Derivatives & Cross-Exchange Funding Rate Heatmap view."""

from __future__ import annotations

from datetime import datetime

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cryptoscope.models.derivatives import (
    DerivativesSnapshot,
    FundingRateEntry,
    LiquidationStats,
    OpenInterestSummary,
)
from cryptoscope.ui.panels import VIEW_DERIVATIVES, build_footer, build_header
import cryptoscope.ui.themes as _themes


class DerivativesView:
    """Manages the Derivatives & Funding Matrix state and rendering."""

    SORT_MODES = ["default", "funding_desc", "funding_asc", "oi_desc", "long_short_desc"]
    TIMEFRAMES = ["1h", "4h", "24h"]

    def __init__(self) -> None:
        self.snapshot: DerivativesSnapshot | None = None
        self.timeframe: str = "4h"
        self.sort_mode: str = "default"
        self.selected_row: int = 0
        self.tickers: list = []  # for header ticker tape
        self.last_update: datetime | None = None
        self.status: str = "OK"
        self.status_msg: str = ""
        self.loading: bool = False

    @property
    def sort_mode_label(self) -> str:
        labels = {
            "default": "Default",
            "funding_desc": "Rate ↓",
            "funding_asc": "Rate ↑",
            "oi_desc": "OI ↓",
            "long_short_desc": "L/S ↓",
        }
        return labels.get(self.sort_mode, self.sort_mode)

    @property
    def keybindings(self) -> list[tuple[str, str]]:
        return [
            ("Esc", "back"),
            ("↑↓", "select"),
            ("s", "sort"),
            ("t", f"tf ({self.timeframe})"),
            ("r", "refresh"),
            ("F7", "settings"),
            ("q", "quit"),
        ]

    def cycle_sort(self) -> None:
        """Cycle through table sort modes."""
        idx = self.SORT_MODES.index(self.sort_mode)
        self.sort_mode = self.SORT_MODES[(idx + 1) % len(self.SORT_MODES)]

    def cycle_timeframe(self) -> None:
        """Cycle liquidation timeframe (1h -> 4h -> 24h -> 1h)."""
        idx = self.TIMEFRAMES.index(self.timeframe)
        self.timeframe = self.TIMEFRAMES[(idx + 1) % len(self.TIMEFRAMES)]

    def select_row(self, delta: int) -> None:
        """Move cursor up or down."""
        entries = self.get_sorted_entries()
        if not entries:
            self.selected_row = 0
            return
        self.selected_row = max(0, min(len(entries) - 1, self.selected_row + delta))

    def get_sorted_entries(self) -> list[FundingRateEntry]:
        """Return funding rate entries sorted according to active sort mode."""
        if not self.snapshot:
            return []
        entries = list(self.snapshot.funding_rates)

        if self.sort_mode == "funding_desc":
            entries.sort(
                key=lambda x: (x.average_funding_rate is not None, x.average_funding_rate or -999.0),
                reverse=True,
            )
        elif self.sort_mode == "funding_asc":
            entries.sort(
                key=lambda x: (x.average_funding_rate is not None, x.average_funding_rate or 999.0),
                reverse=False,
            )
        elif self.sort_mode == "oi_desc":
            entries.sort(
                key=lambda x: (x.open_interest_usd is not None, x.open_interest_usd or -1.0),
                reverse=True,
            )
        elif self.sort_mode == "long_short_desc":
            entries.sort(
                key=lambda x: (x.long_account_ratio is not None, x.long_account_ratio or -1.0),
                reverse=True,
            )

        return entries

    @staticmethod
    def _format_usd(val: float | None) -> str:
        """Format number into human readable currency string."""
        if val is None or val == 0.0:
            return "$0.0"
        if abs(val) >= 1e9:
            return f"${val / 1e9:.1f}B"
        if abs(val) >= 1e6:
            return f"${val / 1e6:.1f}M"
        if abs(val) >= 1e3:
            return f"${val / 1e3:.1f}K"
        return f"${val:.0f}"

    @classmethod
    def format_funding_rate(cls, rate: float | None) -> Text:
        """Format funding rate with heatmap colors and visual indicator emojis.

        Rules:
        - None: '  N/A       ' in grey42
        - Elevated/Extreme Positive (>= +0.0150%): bold red with ' 🔥'
        - Negative (< 0.0%): bold cyan with ' ❄️'
        - Normal Positive (0.0% to +0.0150%): green/bright_white
        """
        if rate is None:
            return Text("  N/A       ", style="grey42")

        pct = rate * 100.0
        pct_str = f"{pct:+.4f}%"

        # Extreme positive funding — long squeeze risk
        if rate >= 0.00015:
            return Text(f"  {pct_str} 🔥", style="bold red")
        # Negative funding — short squeeze risk
        elif rate < 0.0:
            return Text(f"  {pct_str} ❄️", style="bold cyan")
        # Normal positive or zero funding
        elif rate > 0.0:
            return Text(f"  {pct_str}   ", style="green")
        else:
            return Text(f"  {pct_str}   ", style="grey70")

    @classmethod
    def format_long_short_bar(cls, long_ratio: float | None) -> Text:
        """Render 10-char long/short ratio bar, e.g. [██████░░░░] 58%."""
        if long_ratio is None:
            return Text("[──────────] N/A", style="grey42")

        pct = int(round(long_ratio * 100))
        pct = max(0, min(100, pct))
        filled = max(0, min(10, int(round(long_ratio * 10))))
        empty = 10 - filled

        res = Text("[", style="grey50")
        if pct >= 65:
            # Overleveraged longs
            res.append("█" * filled, style="bold red")
            res.append("░" * empty, style="grey27")
            res.append(f"] {pct}%", style="bold red")
        elif pct <= 40:
            # Overleveraged shorts
            res.append("█" * filled, style="bold cyan")
            res.append("░" * empty, style="grey27")
            res.append(f"] {pct}%", style="bold cyan")
        else:
            # Balanced / normal
            res.append("█" * filled, style="bold green")
            res.append("░" * empty, style="grey27")
            res.append(f"] {pct}%", style="bright_white")

        return res

    def _build_global_header_line(self) -> Text:
        """Build the top metric line: Global Open Interest and 24h Liquidations."""
        line = Text()

        if not self.snapshot:
            line.append("Loading live derivatives telemetry...", style="grey50")
            return line

        oi = self.snapshot.open_interest
        liq = self.snapshot.liquidations_24h

        # Global Open Interest
        line.append("Global Open Interest: ", style="bold bright_white")
        if oi and oi.total_open_interest_usd > 0:
            line.append(self._format_usd(oi.total_open_interest_usd), style="bold bright_white")
            change = oi.change_24h_pct
            sign = "+" if change >= 0 else ""
            chg_style = "bold green" if change >= 0 else "bold red"
            line.append(f" ({sign}{change:.1f}% 24h)", style=chg_style)
        else:
            line.append("N/A", style="grey42")

        line.append(" │ ", style=_themes.BORDER_DIM)

        # 24h Liquidations
        line.append("24h Liquidations: ", style="bold bright_white")
        if liq and liq.total_liquidations_usd > 0:
            line.append(self._format_usd(liq.total_liquidations_usd), style="bold yellow")
            line.append(" (", style="grey62")
            line.append(f"Long: {self._format_usd(liq.long_liquidations_usd)}", style="red")
            line.append(" / ", style="grey42")
            line.append(f"Short: {self._format_usd(liq.short_liquidations_usd)}", style="cyan")
            line.append(")", style="grey62")
        else:
            line.append("N/A", style="grey42")

        return line

    def _build_liquidation_barometer(self) -> Panel:
        """Render the Liquidation Barometer for the currently active timeframe."""
        tf_labels = {"1h": "Last 1 Hour", "4h": "Last 4 Hours", "24h": "Last 24 Hours"}
        tf_name = tf_labels.get(self.timeframe, f"Last {self.timeframe}")

        # Fetch stats for current timeframe
        liq_stats: LiquidationStats | None = None
        if self.snapshot and self.snapshot.liquidations_by_tf:
            liq_stats = self.snapshot.liquidations_by_tf.get(self.timeframe)
        if not liq_stats and self.snapshot:
            liq_stats = self.snapshot.liquidations_24h

        long_amt = liq_stats.long_liquidations_usd if liq_stats else 0.0
        short_amt = liq_stats.short_liquidations_usd if liq_stats else 0.0

        max_bar_width = 30
        max_amt = max(long_amt, short_amt)

        if max_amt > 0:
            long_bars = max(1 if long_amt > 0 else 0, int(round((long_amt / max_amt) * max_bar_width)))
            short_bars = max(1 if short_amt > 0 else 0, int(round((short_amt / max_amt) * max_bar_width)))
        else:
            long_bars = 0
            short_bars = 0

        content = Text()
        content.append(f"Liquidation Barometer ({tf_name})  [Key 't' to toggle timeframe]:\n", style="bold white")

        # Long Squeeze row
        content.append("Long Squeeze:  ", style="bold white")
        if long_bars > 0:
            content.append("█" * long_bars, style="bold red")
            content.append(f" ({self._format_usd(long_amt)} liquidated)", style="red")
        else:
            content.append("░" * 4, style="grey27")
            content.append(f" ({self._format_usd(long_amt)} liquidated)", style="grey50")
        content.append("\n")

        # Short Squeeze row
        content.append("Short Squeeze: ", style="bold white")
        if short_bars > 0:
            content.append("█" * short_bars, style="bold cyan")
            content.append(f" ({self._format_usd(short_amt)} liquidated)", style="cyan")
        else:
            content.append("░" * 4, style="grey27")
            content.append(f" ({self._format_usd(short_amt)} liquidated)", style="grey50")

        return Panel(
            content,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
            style=f"on {_themes.BG_SURFACE}",
            height=5,
        )

    def _build_matrix_table(self) -> Table:
        """Render the cross-exchange funding rates and long/short ratio table."""
        table = Table(
            box=_themes.BOX_TABLE,
            expand=True,
            padding=(0, 1),
            header_style="bold grey70",
            show_header=True,
        )

        table.add_column("Coin", justify="left", style="bold white", no_wrap=True, ratio=2)
        table.add_column("Binance Perp", justify="right", no_wrap=True, ratio=2)
        table.add_column("Bybit Perp", justify="right", no_wrap=True, ratio=2)
        table.add_column("OKX Perp", justify="right", no_wrap=True, ratio=2)
        table.add_column("dYdX Perp", justify="right", no_wrap=True, ratio=2)
        table.add_column("24h Long/Short", justify="center", no_wrap=True, ratio=3)

        entries = self.get_sorted_entries()
        if not entries:
            table.add_row(
                Text("Loading...", style="grey50"),
                Text("---", style="grey42"),
                Text("---", style="grey42"),
                Text("---", style="grey42"),
                Text("---", style="grey42"),
                Text("---", style="grey42"),
            )
            return table

        for idx, entry in enumerate(entries):
            is_selected = idx == self.selected_row
            row_style = f"on {_themes.BG_SELECTED}" if is_selected else None

            # Coin column
            coin_text = Text(entry.coin, style="bold bright_white" if is_selected else "bold white")
            if is_selected:
                coin_text = Text("▶ ", style="bold cyan") + coin_text

            # Exchange columns
            b_text = self.format_funding_rate(entry.binance_rate)
            bybit_text = self.format_funding_rate(entry.bybit_rate)
            okx_text = self.format_funding_rate(entry.okx_rate)
            dydx_text = self.format_funding_rate(entry.dydx_rate)

            # Long/short column
            ls_text = self.format_long_short_bar(entry.long_account_ratio)

            table.add_row(
                coin_text,
                b_text,
                bybit_text,
                okx_text,
                dydx_text,
                ls_text,
                style=row_style,
            )

        return table

    def build(self) -> Layout:
        """Build the complete Derivatives & Funding Matrix view."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(build_header(self.tickers))

        # Main container panel
        body_layout = Layout()
        body_layout.split_column(
            Layout(name="matrix", ratio=1),
            Layout(name="barometer", size=5),
        )

        # Header metric line + Table inside one elegant Matrix panel
        matrix_table = self._build_matrix_table()
        matrix_content = Table.grid(expand=True)
        matrix_content.add_column("col", ratio=1)

        header_line = self._build_global_header_line()
        matrix_content.add_row(header_line)
        matrix_content.add_row(Text("─" * 80, style=_themes.BORDER_DIM))
        matrix_content.add_row(matrix_table)

        matrix_title = f"[bold]Derivatives & Funding Matrix[/bold]  [dim]•  Sort: {self.sort_mode_label} ('s' to change)[/dim]"
        matrix_panel = Panel(
            matrix_content,
            title=matrix_title,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_ACTIVE,
            style=f"on {_themes.BG_BASE}",
        )

        body_layout["matrix"].update(matrix_panel)
        body_layout["barometer"].update(self._build_liquidation_barometer())

        layout["body"].update(body_layout)

        layout["footer"].update(
            build_footer(
                active_view=VIEW_DERIVATIVES,
                last_update=self.last_update,
                status=self.status,
                keybindings=self.keybindings,
                error_msg=self.status_msg,
            )
        )

        return layout
