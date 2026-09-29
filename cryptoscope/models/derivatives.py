"""Derivatives data models — funding rates, open interest, and liquidation metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FundingRateEntry:
    """Funding rate entry across multiple derivative exchanges for a coin."""

    coin: str  # e.g. "BTC/USDT"
    symbol: str  # e.g. "BTC"
    binance_rate: float | None = None
    bybit_rate: float | None = None
    okx_rate: float | None = None
    dydx_rate: float | None = None
    long_account_ratio: float | None = None  # e.g. 0.58 for 58%
    short_account_ratio: float | None = None  # e.g. 0.42 for 42%
    open_interest_usd: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    next_funding_time: datetime | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def average_funding_rate(self) -> float | None:
        """Calculate average funding rate across all available exchanges."""
        rates = [
            r
            for r in (self.binance_rate, self.bybit_rate, self.okx_rate, self.dydx_rate)
            if r is not None
        ]
        return sum(rates) / len(rates) if rates else None

    def to_dict(self) -> dict:
        return {
            "coin": self.coin,
            "symbol": self.symbol,
            "binance_rate": self.binance_rate,
            "bybit_rate": self.bybit_rate,
            "okx_rate": self.okx_rate,
            "dydx_rate": self.dydx_rate,
            "long_account_ratio": self.long_account_ratio,
            "short_account_ratio": self.short_account_ratio,
            "open_interest_usd": self.open_interest_usd,
            "mark_price": self.mark_price,
            "index_price": self.index_price,
            "next_funding_time": self.next_funding_time.isoformat() if self.next_funding_time else None,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> FundingRateEntry:
        nft = data.get("next_funding_time")
        ts = data.get("timestamp")
        return cls(
            coin=data["coin"],
            symbol=data["symbol"],
            binance_rate=data.get("binance_rate"),
            bybit_rate=data.get("bybit_rate"),
            okx_rate=data.get("okx_rate"),
            dydx_rate=data.get("dydx_rate"),
            long_account_ratio=data.get("long_account_ratio"),
            short_account_ratio=data.get("short_account_ratio"),
            open_interest_usd=data.get("open_interest_usd"),
            mark_price=data.get("mark_price"),
            index_price=data.get("index_price"),
            next_funding_time=datetime.fromisoformat(nft) if nft else None,
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(),
        )


@dataclass
class OpenInterestSummary:
    """Aggregated global open interest summary."""

    total_open_interest_usd: float = 0.0
    change_24h_pct: float = 0.0
    bybit_oi_usd: float = 0.0
    binance_oi_usd: float = 0.0
    okx_oi_usd: float = 0.0
    dydx_oi_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "total_open_interest_usd": self.total_open_interest_usd,
            "change_24h_pct": self.change_24h_pct,
            "bybit_oi_usd": self.bybit_oi_usd,
            "binance_oi_usd": self.binance_oi_usd,
            "okx_oi_usd": self.okx_oi_usd,
            "dydx_oi_usd": self.dydx_oi_usd,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> OpenInterestSummary:
        ts = data.get("timestamp")
        return cls(
            total_open_interest_usd=float(data.get("total_open_interest_usd", 0.0)),
            change_24h_pct=float(data.get("change_24h_pct", 0.0)),
            bybit_oi_usd=float(data.get("bybit_oi_usd", 0.0)),
            binance_oi_usd=float(data.get("binance_oi_usd", 0.0)),
            okx_oi_usd=float(data.get("okx_oi_usd", 0.0)),
            dydx_oi_usd=float(data.get("dydx_oi_usd", 0.0)),
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(),
        )


@dataclass
class LiquidationStats:
    """Liquidations statistics for a given timeframe (1h, 4h, 24h)."""

    timeframe: str = "24h"
    long_liquidations_usd: float = 0.0
    short_liquidations_usd: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_liquidations_usd(self) -> float:
        return self.long_liquidations_usd + self.short_liquidations_usd

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "long_liquidations_usd": self.long_liquidations_usd,
            "short_liquidations_usd": self.short_liquidations_usd,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> LiquidationStats:
        ts = data.get("timestamp")
        return cls(
            timeframe=data.get("timeframe", "24h"),
            long_liquidations_usd=float(data.get("long_liquidations_usd", 0.0)),
            short_liquidations_usd=float(data.get("short_liquidations_usd", 0.0)),
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(),
        )


@dataclass
class DerivativesSnapshot:
    """Complete snapshot of derivatives market state."""

    open_interest: OpenInterestSummary = field(default_factory=OpenInterestSummary)
    liquidations_24h: LiquidationStats = field(
        default_factory=lambda: LiquidationStats(timeframe="24h")
    )
    liquidations_by_tf: dict[str, LiquidationStats] = field(default_factory=dict)
    funding_rates: list[FundingRateEntry] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "open_interest": self.open_interest.to_dict(),
            "liquidations_24h": self.liquidations_24h.to_dict(),
            "liquidations_by_tf": {
                k: v.to_dict() for k, v in self.liquidations_by_tf.items()
            },
            "funding_rates": [f.to_dict() for f in self.funding_rates],
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DerivativesSnapshot:
        ts = data.get("timestamp")
        oi = OpenInterestSummary.from_dict(data.get("open_interest", {}))
        l24 = LiquidationStats.from_dict(data.get("liquidations_24h", {}))
        ltf = {
            k: LiquidationStats.from_dict(v)
            for k, v in data.get("liquidations_by_tf", {}).items()
        }
        frs = [FundingRateEntry.from_dict(f) for f in data.get("funding_rates", [])]
        return cls(
            open_interest=oi,
            liquidations_24h=l24,
            liquidations_by_tf=ltf,
            funding_rates=frs,
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(),
        )
