"""Whale Alert provider — large transaction monitoring and exchange flow tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from cryptoscope.data.base import DataProvider
from cryptoscope.data.blockchain_com import BlockchainComProvider
from cryptoscope.data.etherscan import EtherscanProvider
from cryptoscope.models.onchain import ExchangeFlow, WhaleTransfer

logger = logging.getLogger(__name__)

WHALE_ALERT_API = "https://api.whale-alert.io/v1"


class WhaleAlertProvider(DataProvider):
    """Monitors transactions above $1,000,000 USD across BTC, ETH, and stablecoins."""

    def __init__(
        self,
        api_key: str = "",
        threshold_usd: float = 1_000_000.0,
        blockchain_provider: BlockchainComProvider | None = None,
        etherscan_provider: EtherscanProvider | None = None,
    ) -> None:
        super().__init__(base_url=WHALE_ALERT_API, api_key=api_key, calls_per_minute=20)
        self.threshold_usd = threshold_usd
        self._blockchain = blockchain_provider
        self._etherscan = etherscan_provider
        self._cache_transfers: list[WhaleTransfer] = []

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        return []

    async def fetch_transfers(self, min_usd: float | None = None) -> list[WhaleTransfer]:
        """Fetch real on-chain whale transfers combined with curated baseline telemetry."""
        threshold = min_usd if min_usd is not None else self.threshold_usd
        transfers: list[WhaleTransfer] = []

        # 1. Fetch live large BTC transactions from Bitcoin mempool & blocks
        if self._blockchain:
            try:
                btc_price = 85_000.0  # reference price for USD estimation
                min_btc = max(1.0, threshold / btc_price)
                btc_txs = await self._blockchain.fetch_recent_large_transactions(min_btc=min_btc)
                for tx in btc_txs:
                    btc_amount = tx["btc"]
                    usd_val = btc_amount * btc_price
                    if usd_val >= threshold:
                        transfers.append(
                            WhaleTransfer(
                                timestamp=tx["timestamp"],
                                blockchain="BTC",
                                symbol="BTC",
                                amount=round(btc_amount, 2),
                                amount_usd=round(usd_val, 2),
                                from_label="Unknown Wallet",
                                to_label="Unknown Wallet",
                                tx_hash=tx["hash"][:16],
                                transfer_type="transfer",
                            )
                        )
            except Exception as e:
                logger.warning("Error fetching live BTC whale transactions: %s", e)

        # 2. Fetch live ETH block transactions from Ethereum RPC
        if self._etherscan:
            try:
                eth_price = 2600.0
                min_eth = max(1.0, threshold / eth_price)
                eth_block_txs = await self._etherscan.fetch_recent_large_transactions(min_eth=min_eth, eth_price=eth_price)
                transfers.extend([t for t in eth_block_txs if t.amount_usd >= threshold])
            except Exception as e:
                logger.warning("Error fetching live ETH block transactions: %s", e)

        # 3. Fetch live ERC-20 transfers if Etherscan provider has API key
        if self._etherscan and self._etherscan.api_key:
            try:
                eth_txs = await self._etherscan.fetch_large_token_transfers(min_usd=threshold)
                transfers.extend(eth_txs)
            except Exception as e:
                logger.warning("Error fetching live ERC-20 whale transfers: %s", e)

        # 4. Query official Whale Alert API if key is present
        if self.api_key:
            try:
                params = {
                    "api_key": self.api_key,
                    "min_value": str(int(threshold)),
                    "limit": "50",
                }
                data = await self._get("/transactions", params=params)
                for item in data.get("transactions", []):
                    transfers.append(
                        WhaleTransfer(
                            timestamp=datetime.fromtimestamp(item.get("timestamp", int(datetime.now().timestamp()))),
                            blockchain=item.get("blockchain", "BTC").upper(),
                            symbol=item.get("symbol", "BTC").upper(),
                            amount=float(item.get("amount", 0.0)),
                            amount_usd=float(item.get("amount_usd", 0.0)),
                            from_address=item.get("from", {}).get("address", ""),
                            from_label=item.get("from", {}).get("owner", "Unknown Wallet") or "Unknown Wallet",
                            to_address=item.get("to", {}).get("address", ""),
                            to_label=item.get("to", {}).get("owner", "Unknown Wallet") or "Unknown Wallet",
                            tx_hash=item.get("hash", ""),
                            transfer_type=item.get("transaction_type", "transfer"),
                        )
                    )
            except Exception as e:
                logger.warning("Whale Alert API error: %s", e)

        # Deduplicate strictly by tx_hash
        seen: set[str] = set()
        deduped: list[WhaleTransfer] = []
        for t in transfers:
            key = t.tx_hash or f"{t.symbol}_{t.amount}_{t.timestamp.strftime('%H:%M:%S')}"
            if key not in seen:
                seen.add(key)
                deduped.append(t)

        deduped.sort(key=lambda x: x.timestamp, reverse=True)
        self._cache_transfers = deduped
        return deduped

    def calculate_exchange_flows(self, transfers: list[WhaleTransfer] | None = None) -> list[ExchangeFlow]:
        """Calculate real net exchange flows from observed on-chain transactions."""
        tx_list = transfers if transfers is not None else self._cache_transfers

        cutoff = datetime.now() - timedelta(hours=24)
        btc_net = 0.0
        eth_net = 0.0

        for t in tx_list:
            if t.timestamp < cutoff:
                continue
            if t.symbol == "BTC":
                if t.is_inflow:
                    btc_net += t.amount
                elif t.is_outflow:
                    btc_net -= t.amount
            elif t.symbol == "ETH":
                if t.is_inflow:
                    eth_net += t.amount
                elif t.is_outflow:
                    eth_net -= t.amount

        btc_classification = (
            "Outflow / Bullish Accumulation" if btc_net < 0
            else "Inflow / Potential Sell Pressure" if btc_net > 0
            else "Neutral / Monitoring Mempool"
        )
        eth_classification = (
            "Inflow / Potential Sell Pressure" if eth_net > 0
            else "Outflow / Bullish Accumulation" if eth_net < 0
            else "Neutral / Monitoring Blocks"
        )

        return [
            ExchangeFlow(
                symbol="BTC",
                net_flow=btc_net,
                flow_usd=abs(btc_net) * 85_000.0,
                classification=btc_classification,
                timestamp=datetime.now(),
            ),
            ExchangeFlow(
                symbol="ETH",
                net_flow=eth_net,
                flow_usd=abs(eth_net) * 2_600.0,
                classification=eth_classification,
                timestamp=datetime.now(),
            ),
        ]
