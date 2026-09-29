"""Etherscan provider for Ethereum gas tracker and token transfers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from cryptoscope.data.base import DataProvider
from cryptoscope.models.onchain import GasPriceInfo, WhaleTransfer

logger = logging.getLogger(__name__)

ETHERSCAN_API = "https://api.etherscan.io"
PUBLIC_RPC_URLS = [
    "https://ethereum-rpc.publicnode.com",
    "https://1rpc.io/eth",
    "https://eth.merkle.io",
]

USDT_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDC_CONTRACT = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


class EtherscanProvider(DataProvider):
    """Etherscan gas tracker and ERC-20 token activity."""

    def __init__(self, api_key: str = "") -> None:
        super().__init__(base_url=ETHERSCAN_API, api_key=api_key, calls_per_minute=20)
        self._rpc_client: httpx.AsyncClient | None = None

    @property
    def rpc_client(self) -> httpx.AsyncClient:
        if self._rpc_client is None or self._rpc_client.is_closed:
            self._rpc_client = httpx.AsyncClient(
                timeout=8.0,
                headers={"Content-Type": "application/json"},
            )
        return self._rpc_client

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        return []

    async def fetch_gas_oracle(self) -> GasPriceInfo:
        """Fetch live gas prices from Etherscan v2 or fallback to public RPC."""
        params: dict[str, str] = {
            "chainid": "1",
            "module": "gastracker",
            "action": "gasoracle",
        }
        if self.api_key:
            params["apikey"] = self.api_key

        try:
            data = await self._get("/v2/api", params=params)
            status = data.get("status")
            result = data.get("result")

            if status == "1" and isinstance(result, dict):
                safe_low = float(result.get("SafeGasPrice", 8.0))
                standard = float(result.get("ProposeGasPrice", 12.0))
                fast = float(result.get("FastGasPrice", 18.0))
                base_fee = float(result.get("suggestBaseFee", 9.4))
                priority_fee = max(0.1, round(standard - base_fee, 1))

                has_key = bool(self.api_key)
                status_msg = "" if has_key else "Free tier (no API key)"

                return GasPriceInfo(
                    safe_low=round(safe_low, 1),
                    standard=round(standard, 1),
                    fast=round(fast, 1),
                    base_fee=round(base_fee, 1),
                    priority_fee=round(priority_fee, 1),
                    source="Etherscan",
                    has_api_key=has_key,
                    status_msg=status_msg,
                    timestamp=datetime.now(),
                )

            logger.info("Etherscan gasoracle returned non-1 status (%s): %s", status, data.get("message"))
        except Exception as e:
            logger.warning("Etherscan gasoracle request failed: %s", e)

        # Fallback to public Ethereum RPC
        return await self._fetch_gas_rpc_fallback()

    async def _fetch_gas_rpc_fallback(self) -> GasPriceInfo:
        """Query public Ethereum JSON-RPC for baseFee and gasPrice."""
        for rpc in PUBLIC_RPC_URLS:
            try:
                # 1. Fetch latest block for base fee
                resp_block = await self.rpc_client.post(
                    rpc,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getBlockByNumber",
                        "params": ["latest", False],
                        "id": 1,
                    },
                )
                if resp_block.status_code == 200:
                    b_data = resp_block.json().get("result", {})
                    base_fee_hex = b_data.get("baseFeePerGas")
                    if base_fee_hex:
                        base_fee = round(int(base_fee_hex, 16) / 1e9, 1)

                        # 2. Fetch current gas price
                        resp_gas = await self.rpc_client.post(
                            rpc,
                            json={
                                "jsonrpc": "2.0",
                                "method": "eth_gasPrice",
                                "params": [],
                                "id": 2,
                            },
                        )
                        standard = base_fee + 2.0
                        if resp_gas.status_code == 200:
                            gas_hex = resp_gas.json().get("result")
                            if gas_hex:
                                standard = round(int(gas_hex, 16) / 1e9, 1)

                        safe_low = max(1.0, round(base_fee + 0.5, 1))
                        fast = max(standard + 2.0, round(base_fee + 5.0, 1))
                        priority_fee = max(0.1, round(standard - base_fee, 1))

                        return GasPriceInfo(
                            safe_low=safe_low,
                            standard=standard,
                            fast=fast,
                            base_fee=base_fee,
                            priority_fee=priority_fee,
                            source="Public RPC",
                            has_api_key=bool(self.api_key),
                            status_msg="RPC fallback (no Etherscan key)" if not self.api_key else "Etherscan fallback",
                            timestamp=datetime.now(),
                        )
            except Exception as e:
                logger.debug("RPC %s failed: %s", rpc, e)

        # Baseline fallback if completely disconnected - strictly real/unavailable metrics
        return GasPriceInfo(
            safe_low=0.0,
            standard=0.0,
            fast=0.0,
            base_fee=0.0,
            priority_fee=0.0,
            source="Unavailable",
            has_api_key=bool(self.api_key),
            status_msg="Offline (RPC unreachable)",
            timestamp=datetime.now(),
        )

    async def fetch_recent_large_transactions(self, min_eth: float = 2.0, eth_price: float = 2600.0) -> list[WhaleTransfer]:
        """Fetch real large ETH transfers from the latest Ethereum block via public RPC."""
        known_addresses = {
            "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
            "0xdfd5293d8e347dff59e4571400cd383922934e81": "Binance",
            "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase",
            "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase",
            "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken",
            "0x6cc5f688a30d37d235c1002071ef485742b96387": "OKX",
            "0xdac17f958d2ee523a2206206994597c13d831ec7": "Tether Contract",
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC Contract",
            "0x0000000000000000000000000000000000000000": "Null Address",
        }

        transfers: list[WhaleTransfer] = []
        for rpc in PUBLIC_RPC_URLS:
            try:
                resp = await self.rpc_client.post(
                    rpc,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getBlockByNumber",
                        "params": ["latest", True],
                        "id": 10,
                    },
                )
                if resp.status_code == 200:
                    b_data = resp.json().get("result", {})
                    time_hex = b_data.get("timestamp", "0x0")
                    block_time = datetime.fromtimestamp(int(time_hex, 16)) if time_hex != "0x0" else datetime.now()
                    txs = b_data.get("transactions", [])
                    for tx in txs:
                        val_hex = tx.get("value", "0x0")
                        val_wei = int(val_hex, 16) if isinstance(val_hex, str) else 0
                        val_eth = val_wei / 1e18
                        if val_eth >= min_eth:
                            from_addr = (tx.get("from") or "").lower()
                            to_addr = (tx.get("to") or "").lower() if tx.get("to") else ""
                            from_label = known_addresses.get(from_addr, "Unknown Wallet")
                            to_label = known_addresses.get(to_addr, "Unknown Wallet")
                            is_mint = from_addr == "0x0000000000000000000000000000000000000000"
                            t_type = "mint" if is_mint else "transfer"

                            transfers.append(
                                WhaleTransfer(
                                    timestamp=block_time,
                                    blockchain="ETH",
                                    symbol="ETH",
                                    amount=round(val_eth, 2),
                                    amount_usd=round(val_eth * eth_price, 2),
                                    from_address=from_addr,
                                    from_label=from_label,
                                    to_address=to_addr,
                                    to_label=to_label,
                                    tx_hash=tx.get("hash", ""),
                                    transfer_type=t_type,
                                )
                            )
                    if transfers or len(txs) > 0:
                        break
            except Exception as e:
                logger.debug("Failed to fetch block transactions from %s: %s", rpc, e)

        return transfers

    async def fetch_large_token_transfers(self, min_usd: float = 1_000_000) -> list[WhaleTransfer]:
        """Fetch large ERC-20 token transfers if API key is provided."""
        if not self.api_key:
            return []

        transfers: list[WhaleTransfer] = []
        for contract, symbol, decimals in [(USDT_CONTRACT, "USDT", 6), (USDC_CONTRACT, "USDC", 6)]:
            params = {
                "chainid": "1",
                "module": "account",
                "action": "tokentx",
                "contractaddress": contract,
                "page": "1",
                "offset": "25",
                "sort": "desc",
                "apikey": self.api_key,
            }
            try:
                data = await self._get("/v2/api", params=params)
                if data.get("status") == "1" and isinstance(data.get("result"), list):
                    for tx in data["result"]:
                        raw_value = float(tx.get("value", 0))
                        amount = raw_value / (10 ** decimals)
                        if amount >= min_usd:
                            transfers.append(
                                WhaleTransfer(
                                    timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                                    blockchain="ETH",
                                    symbol=symbol,
                                    amount=amount,
                                    amount_usd=amount,  # Stablecoins ~ $1
                                    from_address=tx.get("from", ""),
                                    from_label="Unknown Wallet",
                                    to_address=tx.get("to", ""),
                                    to_label="Unknown Wallet",
                                    tx_hash=tx.get("hash", ""),
                                    transfer_type="transfer",
                                )
                            )
            except Exception as e:
                logger.warning("Failed to fetch token transfers for %s: %s", symbol, e)

        return transfers

    async def close(self) -> None:
        await super().close()
        if self._rpc_client and not self._rpc_client.is_closed:
            await self._rpc_client.aclose()
