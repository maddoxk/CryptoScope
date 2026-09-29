"""Blockchain.com and Mempool data provider for Bitcoin network telemetry."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from cryptoscope.data.base import DataProvider
from cryptoscope.models.onchain import MempoolStats

logger = logging.getLogger(__name__)

BLOCKCHAIN_API = "https://api.blockchain.info"
MEMPOOL_SPACE_API = "https://mempool.space/api"


class BlockchainComProvider(DataProvider):
    """Bitcoin network stats: hashrate, difficulty, and mempool congestion."""

    def __init__(self) -> None:
        super().__init__(base_url=BLOCKCHAIN_API, calls_per_minute=30)
        self._mempool_client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=15.0,
                headers=self._default_headers(),
                follow_redirects=True,
            )
        return self._client

    @property
    def mempool_client(self) -> httpx.AsyncClient:
        if self._mempool_client is None or self._mempool_client.is_closed:
            self._mempool_client = httpx.AsyncClient(
                base_url=MEMPOOL_SPACE_API,
                timeout=10.0,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
        return self._mempool_client

    async def fetch_tickers(self, coin_ids: list[str]) -> list:
        """Not applicable for this provider."""
        return []

    async def fetch_network_stats(self) -> MempoolStats:
        """Fetch BTC hashrate, difficulty retarget estimate, and mempool metrics."""
        hashrate_eh = 680.0
        difficulty_t = 92.0
        diff_change_pct = 1.5
        diff_change_days = 3.0
        tx_count = 140000
        size_bytes = 180 * 1024 * 1024

        # 1. Fetch network hashrate and difficulty from blockchain.info/stats
        try:
            stats = await self._get("/stats")
            raw_hashrate = float(stats.get("hash_rate", 0.0))  # in GH/s
            if raw_hashrate > 0:
                # 1 EH/s = 1,000,000,000 GH/s
                hashrate_eh = round(raw_hashrate / 1e9, 1)

            raw_diff = float(stats.get("difficulty", 0.0))
            if raw_diff > 0:
                # 1 Trillion = 1e12
                difficulty_t = round(raw_diff / 1e12, 1)

            current_block = int(stats.get("n_blocks_total", 0))
            next_retarget = int(stats.get("nextretarget", 0))
            min_between_blocks = float(stats.get("minutes_between_blocks", 10.0))

            if next_retarget > current_block and min_between_blocks > 0:
                blocks_remaining = next_retarget - current_block
                diff_change_days = max(0.1, round((blocks_remaining * min_between_blocks) / 1440.0, 1))
                # Target is 10 minutes per block
                diff_change_pct = round(((10.0 / min_between_blocks) - 1.0) * 100.0, 1)
        except Exception as e:
            logger.warning("Failed to fetch blockchain.info stats: %s", e)

        # 2. Fetch mempool metrics (preferred: mempool.space, fallback: blockchain.info)
        mempool_fetched = False
        try:
            resp = await self.mempool_client.get("/mempool")
            if resp.status_code == 200:
                m_data = resp.json()
                tx_count = int(m_data.get("count", tx_count))
                size_bytes = int(m_data.get("vsize", size_bytes))
                mempool_fetched = True
        except Exception as e:
            logger.debug("mempool.space fetch error: %s, trying blockchain.info fallback", e)

        if not mempool_fetched:
            try:
                resp = await self.client.get("/q/unconfirmedcount")
                if resp.status_code == 200:
                    tx_count = int(resp.text.strip())

                chart_data = await self._get("/charts/mempool-size", params={"format": "json", "timespan": "1days"})
                vals = chart_data.get("values", [])
                if vals:
                    size_bytes = int(vals[-1].get("y", size_bytes))
            except Exception as e:
                logger.warning("Blockchain.info mempool fallback failed: %s", e)

        return MempoolStats(
            hashrate_eh=hashrate_eh,
            difficulty_trillion=difficulty_t,
            difficulty_change_pct=diff_change_pct,
            difficulty_change_days=diff_change_days,
            mempool_tx_count=tx_count,
            mempool_size_bytes=size_bytes,
            timestamp=datetime.now(),
        )

    async def fetch_recent_large_transactions(self, min_btc: float = 12.0) -> list[dict[str, Any]]:
        """Fetch large transactions from the latest Bitcoin block."""
        large_txs: list[dict[str, Any]] = []
        try:
            resp = await self.client.get("https://blockchain.info/latestblock")
            if resp.status_code != 200:
                return []
            latest = resp.json()
            block_hash = latest.get("hash")
            if not block_hash:
                return []

            resp_block = await self.client.get(f"https://blockchain.info/rawblock/{block_hash}")
            if resp_block.status_code != 200:
                return []
            block_data = resp_block.json()
            block_time = block_data.get("time", int(datetime.now().timestamp()))
            txs = block_data.get("tx", [])

            for tx in txs:
                total_sats = sum(int(out.get("value", 0)) for out in tx.get("out", []))
                btc = total_sats / 1e8
                if btc >= min_btc:
                    large_txs.append({
                        "hash": tx.get("hash", ""),
                        "btc": btc,
                        "timestamp": datetime.fromtimestamp(block_time),
                        "inputs": tx.get("inputs", []),
                        "outputs": tx.get("out", []),
                    })
        except Exception as e:
            logger.warning("Failed to fetch raw block transactions: %s", e)

        return large_txs

    async def close(self) -> None:
        await super().close()
        if self._mempool_client and not self._mempool_client.is_closed:
            await self._mempool_client.aclose()
