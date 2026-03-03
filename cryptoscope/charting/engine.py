"""Terminal charting engine using plotext."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import plotext as plt
from rich.text import Text

from cryptoscope.models.price import OHLCV

# ── Indicator line colors ──────────────────────────────────────────
# Muted palette that contrasts with candlestick green/red without competing.

SMA_COLORS: dict[int, str] = {
    20: "cyan",
    50: "orange",
    100: "magenta",
    200: "blue+",
}

EMA_COLORS: dict[int, str] = {
    20: "green+",
    50: "yellow",
    100: "magenta+",
    200: "blue",
}

BB_COLOR = "gray+"
DEFAULT_INDICATOR_COLOR = "gray+"

# Braille marker gives the thinnest possible line in plotext.
_MARKER = "braille"


class Timeframe(Enum):
    """Chart timeframes."""

    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"

    @property
    def binance_interval(self) -> str:
        return self.value

    @property
    def coingecko_days(self) -> int:
        mapping = {"1h": 1, "4h": 7, "1d": 30, "1w": 90}
        return mapping[self.value]

    @property
    def label(self) -> str:
        mapping = {"1h": "1 Hour", "4h": "4 Hour", "1d": "1 Day", "1w": "1 Week"}
        return mapping[self.value]


@dataclass
class ChartConfig:
    """Configuration for chart rendering."""

    width: int = 80
    height: int = 25
    show_volume: bool = True
    theme: str = "dark"
    # Indicator toggles
    show_sma: list[int] = field(default_factory=lambda: [20, 50])
    show_ema: list[int] = field(default_factory=list)
    show_bollinger: bool = False
    show_rsi: bool = False
    show_macd: bool = False


def render_candlestick_chart(
    candles: list[OHLCV],
    title: str = "",
    config: ChartConfig | None = None,
    indicators: dict | None = None,
) -> Text:
    """Render a candlestick chart with optional volume and indicators.

    config.width and config.height MUST be set to the available space
    inside the Rich panel that will contain this chart. The caller is
    responsible for calculating these values.

    Returns a Rich Text object with ANSI colors properly converted.
    """
    if not candles:
        return Text("No data available for chart.", style="dim")

    config = config or ChartConfig()
    indicators = indicators or {}

    width = max(40, config.width)
    height = max(10, config.height)

    # How many subplots do we need?
    # SMA/EMA overlay the price chart — no separate subplot.
    # RSI and MACD share one combined indicator subplot.
    has_indicator_panel = (
        (config.show_rsi and "rsi" in indicators)
        or (config.show_macd and "macd_line" in indicators)
    )
    n_subplots = 1  # price always
    if config.show_volume:
        n_subplots += 1
    if has_indicator_panel:
        n_subplots += 1

    plt.clear_figure()
    plt.theme("dark")
    plt.plot_size(width, height)

    if n_subplots > 1:
        plt.subplots(n_subplots, 1)

    # --- Price subplot ---
    subplot_idx = 1
    if n_subplots > 1:
        plt.subplot(subplot_idx, 1)

    dates = [c.timestamp.strftime("%m/%d %H:%M") for c in candles]
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]

    plt.date_form("m/d H:M")

    # Bollinger Bands overlaid on price chart (price-scale, no overlap issue)
    if config.show_bollinger and "bb_upper" in indicators:
        for band_key, label in [("bb_upper", "BB Upper"), ("bb_lower", "BB Lower")]:
            vals = indicators[band_key]
            valid = [(d, v) for d, v in zip(dates, vals) if v is not None]
            if valid:
                d, v = zip(*valid)
                plt.plot(list(d), list(v), label=label, color=BB_COLOR, marker=_MARKER)

    # Overlay SMA lines on price chart
    for period in config.show_sma:
        key = f"sma_{period}"
        if key in indicators:
            vals = indicators[key]
            valid = [(d, v) for d, v in zip(dates, vals) if v is not None]
            if valid:
                dx, vx = zip(*valid)
                plt.plot(
                    list(dx), list(vx),
                    label=f"SMA {period}",
                    color=SMA_COLORS.get(period, DEFAULT_INDICATOR_COLOR),
                    marker=_MARKER,
                )

    # Overlay EMA lines on price chart
    for period in config.show_ema:
        key = f"ema_{period}"
        if key in indicators:
            vals = indicators[key]
            valid = [(d, v) for d, v in zip(dates, vals) if v is not None]
            if valid:
                dx, vx = zip(*valid)
                plt.plot(
                    list(dx), list(vx),
                    label=f"EMA {period}",
                    color=EMA_COLORS.get(period, DEFAULT_INDICATOR_COLOR),
                    marker=_MARKER,
                )

    # Candlesticks drawn after overlays so candle bodies remain visible
    plt.candlestick(dates, {"Open": opens, "Close": closes, "High": highs, "Low": lows})
    plt.title(title or "Price Chart")

    # --- Volume subplot ---
    if config.show_volume:
        subplot_idx += 1
        plt.subplot(subplot_idx, 1)
        volumes = [c.volume for c in candles]
        colors = ["green" if c.close >= c.open else "red" for c in candles]
        plt.bar(dates, volumes, color=colors)
        plt.title("Volume")
        plt.date_form("m/d H:M")

    # --- Combined indicator subplot (RSI and/or MACD) ---
    if has_indicator_panel:
        subplot_idx += 1
        plt.subplot(subplot_idx, 1)
        plt.date_form("m/d H:M")
        ind_labels = []

        if config.show_rsi and "rsi" in indicators:
            rsi_vals = indicators["rsi"]
            valid = [(d, v) for d, v in zip(dates, rsi_vals) if v is not None]
            if valid:
                dx, vx = zip(*valid)
                plt.plot(list(dx), list(vx), label="RSI", color="magenta", marker=_MARKER)
                plt.hline(70, color="red")
                plt.hline(30, color="green")
            ind_labels.append("RSI(14)")

        if config.show_macd and "macd_line" in indicators:
            macd_line = indicators["macd_line"]
            signal_line = indicators["macd_signal"]
            histogram = indicators["macd_histogram"]

            valid_hist = [(d, v) for d, v in zip(dates, histogram) if v is not None]
            valid_macd = [(d, v) for d, v in zip(dates, macd_line) if v is not None]
            valid_sig = [(d, v) for d, v in zip(dates, signal_line) if v is not None]

            if valid_hist:
                dx, vx = zip(*valid_hist)
                hist_colors = ["green" if val >= 0 else "red" for val in vx]
                plt.bar(list(dx), list(vx), color=hist_colors)
            if valid_macd:
                dx, vx = zip(*valid_macd)
                plt.plot(list(dx), list(vx), label="MACD", color="cyan", marker=_MARKER)
            if valid_sig:
                dx, vx = zip(*valid_sig)
                plt.plot(list(dx), list(vx), label="Signal", color="orange", marker=_MARKER)
            ind_labels.append("MACD(12,26,9)")

        plt.title("  /  ".join(ind_labels))

    return Text.from_ansi(plt.build())


def render_line_chart(
    dates: list[str],
    values: list[float],
    title: str = "",
    width: int = 60,
    height: int = 15,
    color: str = "cyan",
) -> Text:
    """Render a simple line chart. Returns Rich Text object."""
    plt.clear_figure()
    plt.theme("dark")
    plt.plot_size(max(30, width), max(8, height))
    plt.date_form("m/d H:M")
    plt.plot(dates, values, color=color)
    if title:
        plt.title(title)
    return Text.from_ansi(plt.build())
