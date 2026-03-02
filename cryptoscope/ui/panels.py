"""Reusable Rich panel components — header, footer, watchlist table, helpers."""

from __future__ import annotations

from datetime import datetime

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cryptoscope.models.price import Ticker
from cryptoscope.ui.themes import (
    BG_SELECTED,
    BG_SURFACE,
    BORDER_DIM,
    BOX_DEFAULT,
    BOX_TABLE,
)
from cryptoscope.utils.formatting import (
    color_percent,
    format_large_number,
    format_price,
    format_volume,
)

# ── Sparkline helpers ──────────────────────────────────────────────

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float], width: int = 8) -> Text:
    """Render a Unicode sparkline from a list of floats.

    Returns a Rich Text object colored green if the trend is up, red if down.
    """
    if not values:
        return Text("—" * width, style="grey42")

    # Take the last `width` values
    vals = values[-width:]
    lo, hi = min(vals), max(vals)
    span = hi - lo if hi != lo else 1.0

    color = "green" if vals[-1] >= vals[0] else "red"

    spark = Text()
    for v in vals:
        idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        spark.append(_SPARK_CHARS[idx], style=color)

    return spark


def _volume_bar(volume: float, max_volume: float, width: int = 6) -> Text:
    """Render a mini volume bar — filled in cornflower_blue, empty in grey19."""
    if max_volume <= 0:
        return Text("░" * width, style="grey19")

    filled = int((volume / max_volume) * width)
    filled = max(0, min(width, filled))

    bar = Text()
    bar.append("█" * filled, style="cornflower_blue")
    bar.append("░" * (width - filled), style="grey19")
    return bar


# ── Header ─────────────────────────────────────────────────────────


def build_header(tickers: list[Ticker] | None = None) -> Panel:
    """Build the top header bar with brand, ticker tape, and clock.

    Accepts the full ticker list and shows the top 5 coins as a scrolling
    tape with price + 24h change.
    """
    now = datetime.now().strftime("%H:%M:%S")

    # Use an inner table for left/right alignment
    header_table = Table.grid(expand=True)
    header_table.add_column("left", ratio=1)
    header_table.add_column("right", justify="right")

    # Left side: brand + ticker tape
    left = Text()
    left.append(" CRYPTOSCOPE ", style="bold cornflower_blue")
    left.append(" ", style="grey27")

    if tickers:
        for i, t in enumerate(tickers[:5]):
            if i > 0:
                left.append("  │  ", style="grey27")
            left.append(f"{t.symbol} ", style="bold white")
            left.append(format_price(t.price_usd), style="bright_white")
            left.append(" ")
            pct = t.change_24h
            sign = "+" if pct > 0 else ""
            style = "bold green" if pct > 0 else "bold red" if pct < 0 else "grey50"
            left.append(f"{sign}{pct:.1f}%", style=style)
    else:
        left.append("Loading...", style="grey42")

    # Right side: clock
    right = Text()
    right.append(now, style="grey70")
    right.append(" ")

    header_table.add_row(left, right)

    return Panel(
        header_table,
        box=BOX_DEFAULT,
        border_style=BORDER_DIM,
        style=f"on {BG_SURFACE}",
        height=3,
    )


# ── Footer ─────────────────────────────────────────────────────────

# View name constants for tab bar
VIEW_WATCHLIST = "watchlist"
VIEW_CHART = "chart"
VIEW_SENTIMENT = "sentiment"


def build_footer(
    active_view: str,
    last_update: datetime | None = None,
    status: str = "OK",
    keybindings: list[tuple[str, str]] | None = None,
) -> Panel:
    """Build the shared footer bar used by all views.

    Layout: [tab bar] | [status dot + timestamp] | [keybindings]
    """
    footer = Table.grid(expand=True)
    footer.add_column("tabs", ratio=1)
    footer.add_column("status", justify="center", ratio=1)
    footer.add_column("keys", justify="right", ratio=2)

    # --- Tab bar ---
    tabs = Text()
    tab_defs = [
        ("F1", "Watchlist", VIEW_WATCHLIST),
        ("F2", "Sentiment", VIEW_SENTIMENT),
    ]
    for key, label, view_id in tab_defs:
        if view_id == active_view:
            tabs.append(f" {key} {label} ", style=f"bold bright_white on {BG_SELECTED}")
        else:
            tabs.append(f" {key} {label} ", style=f"grey50 on {BG_SURFACE}")
        tabs.append(" ")

    # --- Status ---
    status_text = Text()
    dot_style = "bold green" if status == "OK" else "bold red"
    status_text.append(" ● ", style=dot_style)
    if last_update:
        status_text.append(last_update.strftime("%H:%M:%S"), style="grey70")
    else:
        status_text.append("---", style="grey42")

    # --- Keybindings ---
    keys_text = Text()
    if keybindings:
        for key, action in keybindings:
            keys_text.append(f"{key}", style="bold cornflower_blue")
            keys_text.append(f" {action}  ", style="grey62")

    footer.add_row(tabs, status_text, keys_text)

    return Panel(
        footer,
        box=BOX_DEFAULT,
        border_style=BORDER_DIM,
        style=f"on {BG_SURFACE}",
        height=3,
    )


# ── Watchlist Table ────────────────────────────────────────────────


def build_watchlist_table(
    tickers: list[Ticker],
    selected_row: int = -1,
    price_history: dict[str, list[float]] | None = None,
) -> Table:
    """Build the main watchlist table with sparklines and volume bars."""
    if price_history is None:
        price_history = {}

    table = Table(
        box=BOX_TABLE,
        show_header=True,
        header_style="bold grey70",
        border_style=BORDER_DIM,
        expand=True,
        pad_edge=True,
        row_styles=["", f"on grey7"],
    )

    table.add_column("#", style="grey50", width=4, justify="right")
    table.add_column("Coin", min_width=14)
    table.add_column("Price", justify="right", min_width=12)
    table.add_column("1h", justify="right", min_width=8)
    table.add_column("24h", justify="right", min_width=8)
    table.add_column("7d", justify="right", min_width=8)
    table.add_column("Vol 24h", justify="right", min_width=10)
    table.add_column("Vol", justify="center", width=6)
    table.add_column("Mkt Cap", justify="right", min_width=12)
    table.add_column("7d", justify="center", width=8)

    # Find max volume for volume bars
    max_vol = max((t.volume_24h for t in tickers), default=1) if tickers else 1

    for idx, ticker in enumerate(tickers):
        row_style = f"bold on {BG_SELECTED}" if idx == selected_row else ""

        # Sparkline from price history
        history = price_history.get(ticker.id, [])
        spark = _sparkline(history)

        # Volume bar
        vol_bar = _volume_bar(ticker.volume_24h, max_vol)

        table.add_row(
            str(ticker.market_cap_rank),
            Text.assemble(
                (f"{ticker.symbol}", "bold bright_white"),
                " ",
                (ticker.name, "grey62"),
            ),
            Text(format_price(ticker.price_usd), style="bold bright_white"),
            Text.from_markup(color_percent(ticker.change_1h)),
            Text.from_markup(color_percent(ticker.change_24h)),
            Text.from_markup(color_percent(ticker.change_7d)),
            format_volume(ticker.volume_24h),
            vol_bar,
            format_large_number(ticker.market_cap),
            spark,
            style=row_style,
        )

    return table
