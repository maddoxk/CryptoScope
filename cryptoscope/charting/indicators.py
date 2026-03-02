"""Technical indicators computed locally with pandas."""

from __future__ import annotations

import pandas as pd

from cryptoscope.models.price import OHLCV


def candles_to_df(candles: list[OHLCV]) -> pd.DataFrame:
    """Convert a list of OHLCV candles to a pandas DataFrame."""
    return pd.DataFrame(
        {
            "timestamp": [c.timestamp for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )


def sma(df: pd.DataFrame, period: int = 20) -> list[float | None]:
    """Simple Moving Average."""
    series = df["close"].rolling(window=period).mean()
    return [None if pd.isna(v) else v for v in series]


def ema(df: pd.DataFrame, period: int = 20) -> list[float | None]:
    """Exponential Moving Average."""
    series = df["close"].ewm(span=period, adjust=False).mean()
    return [None if pd.isna(v) else v for v in series]


def rsi(df: pd.DataFrame, period: int = 14) -> list[float | None]:
    """Relative Strength Index."""
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_values = 100 - (100 / (1 + rs))

    return [None if pd.isna(v) else v for v in rsi_values]


def macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD (Moving Average Convergence Divergence).

    Returns (macd_line, signal_line, histogram).
    """
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    def to_list(s: pd.Series) -> list[float | None]:
        return [None if pd.isna(v) else v for v in s]

    return to_list(macd_line), to_list(signal_line), to_list(histogram)


def bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands.

    Returns (upper_band, middle_band, lower_band).
    """
    middle = df["close"].rolling(window=period).mean()
    rolling_std = df["close"].rolling(window=period).std()
    upper = middle + (rolling_std * std_dev)
    lower = middle - (rolling_std * std_dev)

    def to_list(s: pd.Series) -> list[float | None]:
        return [None if pd.isna(v) else v for v in s]

    return to_list(upper), to_list(middle), to_list(lower)


def vwap(df: pd.DataFrame) -> list[float | None]:
    """Volume-Weighted Average Price."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    vwap_series = cum_tp_vol / cum_vol

    return [None if pd.isna(v) else v for v in vwap_series]


def compute_all_indicators(
    candles: list[OHLCV],
    sma_periods: list[int] | None = None,
    ema_periods: list[int] | None = None,
    include_rsi: bool = True,
    include_macd: bool = True,
    include_bollinger: bool = True,
    include_vwap: bool = True,
) -> dict[str, list[float | None]]:
    """Compute all requested indicators and return as a dict.

    Keys: sma_20, sma_50, ema_20, rsi, macd_line, macd_signal,
          macd_histogram, bb_upper, bb_middle, bb_lower, vwap
    """
    if sma_periods is None:
        sma_periods = [20, 50, 200]
    if ema_periods is None:
        ema_periods = [20, 50, 200]

    df = candles_to_df(candles)
    result: dict[str, list[float | None]] = {}

    for period in sma_periods:
        if len(df) >= period:
            result[f"sma_{period}"] = sma(df, period)

    for period in ema_periods:
        result[f"ema_{period}"] = ema(df, period)

    if include_rsi:
        result["rsi"] = rsi(df)

    if include_macd:
        macd_l, macd_s, macd_h = macd(df)
        result["macd_line"] = macd_l
        result["macd_signal"] = macd_s
        result["macd_histogram"] = macd_h

    if include_bollinger:
        bb_u, bb_m, bb_l = bollinger_bands(df)
        result["bb_upper"] = bb_u
        result["bb_middle"] = bb_m
        result["bb_lower"] = bb_l

    if include_vwap and any(c.volume > 0 for c in candles):
        result["vwap"] = vwap(df)

    return result
