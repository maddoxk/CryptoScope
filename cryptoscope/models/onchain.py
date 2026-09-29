"""On-chain analytics and whale tracking data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

KNOWN_EXCHANGES = {
    "binance", "coinbase", "kraken", "okx", "bybit",
    "bitfinex", "huobi", "gemini", "kucoin", "bitstamp",
    "gate.io", "mexc", "deribit", "crypto.com",
}


@dataclass
class GasPriceInfo:
    """Ethereum EIP-1559 and legacy gas price tiers."""

    safe_low: float              # Safe / Low gas price in Gwei
    standard: float              # Standard / Average / Proposed in Gwei
    fast: float                  # Fast / High in Gwei
    base_fee: float = 0.0        # EIP-1559 base fee in Gwei
    priority_fee: float = 0.0    # Priority fee in Gwei
    source: str = "Etherscan"
    has_api_key: bool = True
    status_msg: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe_low": self.safe_low,
            "standard": self.standard,
            "fast": self.fast,
            "base_fee": self.base_fee,
            "priority_fee": self.priority_fee,
            "source": self.source,
            "has_api_key": self.has_api_key,
            "status_msg": self.status_msg,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GasPriceInfo:
        ts = (
            datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data and isinstance(data["timestamp"], str)
            else datetime.now()
        )
        return cls(
            safe_low=float(data.get("safe_low", 0.0)),
            standard=float(data.get("standard", 0.0)),
            fast=float(data.get("fast", 0.0)),
            base_fee=float(data.get("base_fee", 0.0)),
            priority_fee=float(data.get("priority_fee", 0.0)),
            source=data.get("source", "Etherscan"),
            has_api_key=data.get("has_api_key", True),
            status_msg=data.get("status_msg", ""),
            timestamp=ts,
        )


@dataclass
class MempoolStats:
    """Bitcoin network health, difficulty, and mempool congestion."""

    hashrate_eh: float                  # Hashrate in EH/s
    difficulty_trillion: float          # Difficulty in Trillion (T)
    difficulty_change_pct: float = 0.0  # Estimated next difficulty change %
    difficulty_change_days: float = 0.0 # Estimated days to next difficulty adjustment
    mempool_tx_count: int = 0           # Unconfirmed transactions count
    mempool_size_bytes: int = 0         # Mempool size in bytes
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def mempool_size_mb(self) -> float:
        return self.mempool_size_bytes / (1024 * 1024)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hashrate_eh": self.hashrate_eh,
            "difficulty_trillion": self.difficulty_trillion,
            "difficulty_change_pct": self.difficulty_change_pct,
            "difficulty_change_days": self.difficulty_change_days,
            "mempool_tx_count": self.mempool_tx_count,
            "mempool_size_bytes": self.mempool_size_bytes,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MempoolStats:
        ts = (
            datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data and isinstance(data["timestamp"], str)
            else datetime.now()
        )
        return cls(
            hashrate_eh=float(data.get("hashrate_eh", 0.0)),
            difficulty_trillion=float(data.get("difficulty_trillion", 0.0)),
            difficulty_change_pct=float(data.get("difficulty_change_pct", 0.0)),
            difficulty_change_days=float(data.get("difficulty_change_days", 0.0)),
            mempool_tx_count=int(data.get("mempool_tx_count", 0)),
            mempool_size_bytes=int(data.get("mempool_size_bytes", 0)),
            timestamp=ts,
        )


@dataclass
class ExchangeFlow:
    """24h Exchange Net Flow metrics for a cryptocurrency."""

    symbol: str                         # "BTC", "ETH"
    net_flow: float                     # negative = outflow, positive = inflow
    flow_usd: float = 0.0
    classification: str = ""            # e.g. "Outflow / Bullish Accumulation"
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_outflow(self) -> bool:
        return self.net_flow < 0

    @property
    def is_inflow(self) -> bool:
        return self.net_flow > 0

    @property
    def resolved_classification(self) -> str:
        if self.classification:
            return self.classification
        if self.net_flow < 0:
            return "Outflow / Bullish Accumulation"
        elif self.net_flow > 0:
            return "Inflow / Potential Sell Pressure"
        return "Neutral Flow"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "net_flow": self.net_flow,
            "flow_usd": self.flow_usd,
            "classification": self.resolved_classification,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeFlow:
        ts = (
            datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data and isinstance(data["timestamp"], str)
            else datetime.now()
        )
        return cls(
            symbol=data.get("symbol", "BTC"),
            net_flow=float(data.get("net_flow", 0.0)),
            flow_usd=float(data.get("flow_usd", 0.0)),
            classification=data.get("classification", ""),
            timestamp=ts,
        )


@dataclass
class WhaleTransfer:
    """Individual large on-chain transaction alert (> threshold)."""

    timestamp: datetime
    blockchain: str                     # "BTC", "ETH", "USDT", "USDC"
    symbol: str                         # "BTC", "ETH", "USDT"
    amount: float
    amount_usd: float
    from_address: str = ""
    from_label: str = "Unknown Wallet"
    to_address: str = ""
    to_label: str = "Unknown Wallet"
    tx_hash: str = ""
    transfer_type: str = "transfer"     # "transfer", "mint", "burn"

    @property
    def is_inflow(self) -> bool:
        """Transferred from a wallet to an exchange (potential sell pressure)."""
        f_norm = self.from_label.lower()
        t_norm = self.to_label.lower()
        from_is_exchange = any(ex in f_norm for ex in KNOWN_EXCHANGES)
        to_is_exchange = any(ex in t_norm for ex in KNOWN_EXCHANGES)
        return to_is_exchange and not from_is_exchange

    @property
    def is_outflow(self) -> bool:
        """Transferred from an exchange to a wallet/cold storage (bullish accumulation)."""
        f_norm = self.from_label.lower()
        t_norm = self.to_label.lower()
        from_is_exchange = any(ex in f_norm for ex in KNOWN_EXCHANGES)
        to_is_exchange = any(ex in t_norm for ex in KNOWN_EXCHANGES)
        return from_is_exchange and not to_is_exchange

    @property
    def is_mint(self) -> bool:
        return self.transfer_type.lower() == "mint" or "mint" in self.transfer_type.lower()

    @property
    def flow_color(self) -> str:
        if self.is_inflow:
            return "red"
        elif self.is_outflow:
            return "green"
        elif self.is_mint:
            return "cyan"
        return "bright_white"

    @property
    def formatted_time(self) -> str:
        return self.timestamp.strftime("[%H:%M]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "blockchain": self.blockchain,
            "symbol": self.symbol,
            "amount": self.amount,
            "amount_usd": self.amount_usd,
            "from_address": self.from_address,
            "from_label": self.from_label,
            "to_address": self.to_address,
            "to_label": self.to_label,
            "tx_hash": self.tx_hash,
            "transfer_type": self.transfer_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WhaleTransfer:
        ts = (
            datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data and isinstance(data["timestamp"], str)
            else datetime.now()
        )
        return cls(
            timestamp=ts,
            blockchain=data.get("blockchain", "BTC"),
            symbol=data.get("symbol", "BTC"),
            amount=float(data.get("amount", 0.0)),
            amount_usd=float(data.get("amount_usd", 0.0)),
            from_address=data.get("from_address", ""),
            from_label=data.get("from_label", "Unknown Wallet"),
            to_address=data.get("to_address", ""),
            to_label=data.get("to_label", "Unknown Wallet"),
            tx_hash=data.get("tx_hash", ""),
            transfer_type=data.get("transfer_type", "transfer"),
        )
