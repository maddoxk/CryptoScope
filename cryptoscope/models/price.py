"""Price and market data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Ticker:
    """Current price ticker for a coin."""

    id: str
    symbol: str
    name: str
    price_usd: float
    market_cap: float = 0.0
    volume_24h: float = 0.0
    change_1h: float = 0.0
    change_24h: float = 0.0
    change_7d: float = 0.0
    market_cap_rank: int = 0
    circulating_supply: float = 0.0
    max_supply: float | None = None
    ath: float = 0.0
    atl: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class OHLCV:
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderBookEntry:
    """Single order book level."""

    price: float
    quantity: float


@dataclass
class OrderBook:
    """Order book snapshot."""

    symbol: str
    bids: list[OrderBookEntry] = field(default_factory=list)
    asks: list[OrderBookEntry] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
