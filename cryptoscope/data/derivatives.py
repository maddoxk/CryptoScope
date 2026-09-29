"""Derivatives data provider — real live cross-exchange funding rates, open interest, and liquidations."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from cryptoscope.models.derivatives import (
    DerivativesSnapshot,
    FundingRateEntry,
    LiquidationStats,
    OpenInterestSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_COINS = [
    "BTC",
    "ETH",
    "SOL",
    "DOGE",
    "XRP",
    "ADA",
    "AVAX",
    "BNB",
    "LINK",
    "SUI",
    "NEAR",
    "APT",
]


class DerivativesProvider:
    """Async provider integrating Binance Futures, Bybit, OKX, dYdX, and CoinGlass."""

    def __init__(
        self,
        coinglass_api_key: str = "",
        db: Any | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.coinglass_api_key = coinglass_api_key
        self.db = db
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        # In-memory cache fallback: key -> (value, expire_timestamp)
        self._memory_cache: dict[str, tuple[Any, float]] = {}

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"User-Agent": "CryptoScope-Terminal/1.0", "Accept": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Close underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Cache Helpers ──────────────────────────────────────────────────

    async def _get_cached(self, key: str) -> Any | None:
        """Check DB cache if available, otherwise check memory cache."""
        now = time.time()
        if self.db and getattr(self.db, "_db", None) is not None:
            try:
                cached = await self.db.cache_get(key)
                if cached is not None:
                    return cached
            except Exception as e:
                logger.debug("DB cache get error for %s: %s", key, e)

        if key in self._memory_cache:
            data, expires_at = self._memory_cache[key]
            if now < expires_at:
                return data
            del self._memory_cache[key]
        return None

    async def _set_cached(self, key: str, data: Any, ttl_seconds: int) -> None:
        """Store into DB cache and in-memory cache."""
        now = time.time()
        self._memory_cache[key] = (data, now + ttl_seconds)
        if self.db and getattr(self.db, "_db", None) is not None:
            try:
                await self.db.cache_set(key, data, ttl_seconds=ttl_seconds)
            except Exception as e:
                logger.debug("DB cache set error for %s: %s", key, e)

    # ── Binance Futures Public Data ────────────────────────────────────

    async def fetch_binance_premium_indexes(self) -> dict[str, dict[str, Any]]:
        """Fetch real-time funding rates, mark/index prices from Binance Futures premiumIndex.

        Cached for 60 seconds.
        Returns a dict mapping symbol (e.g. 'BTCUSDT') to premium index dict.
        """
        cache_key = "deriv_binance_premium_indexes"
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            result: dict[str, dict[str, Any]] = {}
            if isinstance(data, list):
                for item in data:
                    sym = item.get("symbol")
                    if sym:
                        result[sym] = item
            elif isinstance(data, dict) and "symbol" in data:
                result[data["symbol"]] = data

            if result:
                await self._set_cached(cache_key, result, ttl_seconds=60)
            return result
        except Exception as e:
            logger.warning("Binance premiumIndex fetch failed: %s", e)
            return {}

    async def fetch_binance_long_short_ratios(
        self, symbols: list[str]
    ) -> dict[str, tuple[float | None, float | None]]:
        """Fetch 24h global long/short account ratio for given symbols from Binance.

        Cached for 60 seconds.
        Returns dict mapping symbol -> (long_ratio, short_ratio).
        """
        cache_key = "deriv_binance_long_short_ratios"
        cached = await self._get_cached(cache_key)
        if cached:
            return {k: tuple(v) for k, v in cached.items()}

        async def _fetch_one(sym: str) -> tuple[str, float | None, float | None]:
            url = (
                f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
                f"?symbol={sym}&period=1d&limit=1"
            )
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    items = resp.json()
                    if items and isinstance(items, list):
                        entry = items[0]
                        long_acc = float(entry.get("longAccount", 0.0))
                        short_acc = float(entry.get("shortAccount", 0.0))
                        return sym, long_acc, short_acc
            except Exception as e:
                logger.debug("Failed long/short ratio for %s: %s", sym, e)
            return sym, None, None

        tasks = [_fetch_one(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ratio_map: dict[str, tuple[float | None, float | None]] = {}
        for r in results:
            if isinstance(r, tuple) and len(r) == 3:
                sym, long_acc, short_acc = r
                ratio_map[sym] = (long_acc, short_acc)

        if ratio_map:
            # Store as list in cache for JSON compatibility
            serializable = {k: list(v) for k, v in ratio_map.items()}
            await self._set_cached(cache_key, serializable, ttl_seconds=60)

        return ratio_map

    async def fetch_binance_open_interest_stats(self) -> tuple[float, float]:
        """Fetch Binance BTC open interest USD value and 24h % change.

        Cached for 30 seconds.
        Returns (btc_oi_usd, change_24h_pct).
        """
        cache_key = "deriv_binance_oi_stats"
        cached = await self._get_cached(cache_key)
        if cached:
            return float(cached[0]), float(cached[1])

        url = "https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=1h&limit=25"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) >= 2:
                v_start = float(data[0].get("sumOpenInterestValue") or 0.0)
                v_end = float(data[-1].get("sumOpenInterestValue") or 0.0)
                pct_change = ((v_end - v_start) / v_start * 100.0) if v_start > 0 else 0.0
                await self._set_cached(cache_key, [v_end, pct_change], ttl_seconds=30)
                return v_end, pct_change
            elif isinstance(data, list) and len(data) == 1:
                v_end = float(data[-1].get("sumOpenInterestValue") or 0.0)
                return v_end, 0.0
        except Exception as e:
            logger.warning("Binance openInterestHist fetch failed: %s", e)
        return 0.0, 0.0

    # ── Bybit v5 Public Linear Tickers ─────────────────────────────────

    async def fetch_bybit_linear_tickers(self) -> tuple[dict[str, dict[str, Any]], float]:
        """Fetch Bybit v5 linear tickers for funding rates and total linear Open Interest.

        Cached for 30 seconds for OI, 60 seconds for rates.
        Returns (symbol_map, total_bybit_oi_usd).
        """
        cache_key = "deriv_bybit_linear_tickers"
        cached = await self._get_cached(cache_key)
        if cached:
            return cached.get("tickers", {}), float(cached.get("total_oi", 0.0))

        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            ticker_list = data.get("result", {}).get("list", [])
            ticker_map: dict[str, dict[str, Any]] = {}
            total_oi = 0.0

            for t in ticker_list:
                sym = t.get("symbol")
                if sym:
                    ticker_map[sym] = t
                oi_val = float(t.get("openInterestValue") or 0.0)
                total_oi += oi_val

            store = {"tickers": ticker_map, "total_oi": total_oi}
            await self._set_cached(cache_key, store, ttl_seconds=30)
            return ticker_map, total_oi
        except Exception as e:
            logger.warning("Bybit linear tickers fetch failed: %s", e)
            return {}, 0.0

    # ── OKX v5 Public REST API ─────────────────────────────────────────

    async def fetch_okx_funding_rates(self, coins: list[str]) -> dict[str, float | None]:
        """Fetch live funding rates from OKX public endpoint for given coins.

        Cached for 60 seconds.
        Returns dict mapping coin (e.g. 'BTC') to funding rate float.
        """
        cache_key = f"deriv_okx_funding_rates_{','.join(sorted(coins))}"
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        async def _fetch_one(coin: str) -> tuple[str, float | None]:
            url = f"https://www.okx.com/api/v5/public/funding-rate?instId={coin}-USDT-SWAP"
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    if items:
                        rate = float(items[0].get("fundingRate") or 0.0)
                        return coin, rate
            except Exception as e:
                logger.debug("OKX funding rate failed for %s: %s", coin, e)
            return coin, None

        tasks = [_fetch_one(c) for c in coins]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        rate_map: dict[str, float | None] = {}
        for r in results:
            if isinstance(r, tuple) and len(r) == 2:
                coin, rate = r
                rate_map[coin] = rate

        if rate_map:
            await self._set_cached(cache_key, rate_map, ttl_seconds=60)
        return rate_map

    async def fetch_okx_liquidations(
        self, coins: list[str]
    ) -> dict[str, LiquidationStats]:
        """Fetch filled liquidation orders from OKX for given coins and aggregate by timeframe.

        Returns dict: {"1h": LiquidationStats, "4h": LiquidationStats, "24h": LiquidationStats}.
        Cached for 30 seconds.
        """
        cache_key = f"deriv_okx_liquidations_{','.join(sorted(coins))}"
        cached = await self._get_cached(cache_key)
        if cached:
            return {k: LiquidationStats.from_dict(v) for k, v in cached.items()}

        now_ms = int(time.time() * 1000)

        async def _fetch_coin_liquidations(coin: str) -> list[dict[str, Any]]:
            url = (
                f"https://www.okx.com/api/v5/public/liquidation-orders"
                f"?instType=SWAP&mgnMode=cross&instFamily={coin}-USDT&state=filled"
            )
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    orders = data.get("data", [])
                    all_details = []
                    for order in orders:
                        all_details.extend(order.get("details", []))
                    return all_details
            except Exception as e:
                logger.debug("OKX liquidation orders failed for %s: %s", coin, e)
            return []

        tasks = [_fetch_coin_liquidations(c) for c in coins]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        long_1h, short_1h = 0.0, 0.0
        long_4h, short_4h = 0.0, 0.0
        long_24h, short_24h = 0.0, 0.0

        for r in results:
            if isinstance(r, list):
                for item in r:
                    ts = int(item.get("ts") or item.get("time") or 0)
                    sz = float(item.get("sz") or 0.0)
                    px = float(item.get("bkPx") or 0.0)
                    val_usd = sz * px
                    pos_side = str(item.get("posSide", "")).lower()

                    age_ms = now_ms - ts
                    if age_ms <= 24 * 3600 * 1000:
                        if pos_side == "long":
                            long_24h += val_usd
                        elif pos_side == "short":
                            short_24h += val_usd

                    if age_ms <= 4 * 3600 * 1000:
                        if pos_side == "long":
                            long_4h += val_usd
                        elif pos_side == "short":
                            short_4h += val_usd

                    if age_ms <= 1 * 3600 * 1000:
                        if pos_side == "long":
                            long_1h += val_usd
                        elif pos_side == "short":
                            short_1h += val_usd

        stats_by_tf = {
            "1h": LiquidationStats(timeframe="1h", long_liquidations_usd=long_1h, short_liquidations_usd=short_1h),
            "4h": LiquidationStats(timeframe="4h", long_liquidations_usd=long_4h, short_liquidations_usd=short_4h),
            "24h": LiquidationStats(timeframe="24h", long_liquidations_usd=long_24h, short_liquidations_usd=short_24h),
        }

        serializable = {k: v.to_dict() for k, v in stats_by_tf.items()}
        await self._set_cached(cache_key, serializable, ttl_seconds=30)
        return stats_by_tf

    # ── dYdX v4 Indexer REST API ───────────────────────────────────────

    async def fetch_dydx_markets(self) -> dict[str, dict[str, Any]]:
        """Fetch perpetual markets from dYdX v4 Indexer API.

        Cached for 60 seconds.
        Returns dict mapping ticker (e.g. 'BTC-USD') to market details.
        """
        cache_key = "deriv_dydx_markets"
        cached = await self._get_cached(cache_key)
        if cached:
            return cached

        url = "https://indexer.dydx.trade/v4/perpetualMarkets"
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            markets = data.get("markets", {})
            if markets:
                await self._set_cached(cache_key, markets, ttl_seconds=60)
            return markets
        except Exception as e:
            logger.warning("dYdX perpetualMarkets fetch failed: %s", e)
            return {}

    # ── CoinGlass Client (Optional Authenticated) ──────────────────────

    async def fetch_coinglass_liquidations(self) -> LiquidationStats | None:
        """Fetch liquidations from CoinGlass if an API key is provided."""
        if not self.coinglass_api_key:
            return None

        cache_key = "deriv_coinglass_liquidations"
        cached = await self._get_cached(cache_key)
        if cached:
            return LiquidationStats.from_dict(cached)

        headers = {
            "CG-API-KEY": self.coinglass_api_key,
            "coinglassSecret": self.coinglass_api_key,
        }
        url = "https://open-api-v3.coinglass.com/api/futures/liquidation/detail/chart?symbol=all&time_type=all"
        try:
            resp = await self.client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and "data" in data:
                    cdata = data["data"]
                    long_vol = float(cdata.get("longVolUsd") or 0.0)
                    short_vol = float(cdata.get("shortVolUsd") or 0.0)
                    stats = LiquidationStats(
                        timeframe="24h",
                        long_liquidations_usd=long_vol,
                        short_liquidations_usd=short_vol,
                    )
                    await self._set_cached(cache_key, stats.to_dict(), ttl_seconds=60)
                    return stats
        except Exception as e:
            logger.debug("CoinGlass liquidations fetch error: %s", e)
        return None

    # ── Master Snapshot Aggregator ─────────────────────────────────────

    async def fetch_derivatives_snapshot(
        self,
        coins: list[str] | None = None,
        force_refresh: bool = False,
    ) -> DerivativesSnapshot:
        """Concurrently fetch and combine derivatives data from all live public sources.

        No mock or fake seed data is used anywhere. If a source is down or has no data,
        it will cleanly be None / 0.0 and displayed as N/A.
        """
        tracked_coins = list(coins) if coins else list(DEFAULT_COINS)

        # Clear memory caches if force_refresh requested
        if force_refresh:
            self._memory_cache.clear()

        binance_symbols = [f"{c}USDT" for c in tracked_coins]

        # Concurrently fetch all independent sources
        (
            binance_indexes,
            binance_ratios,
            binance_oi_stats,
            (bybit_tickers, total_bybit_oi),
            okx_rates,
            okx_liquidations,
            dydx_markets,
            coinglass_stats,
        ) = await asyncio.gather(
            self.fetch_binance_premium_indexes(),
            self.fetch_binance_long_short_ratios(binance_symbols),
            self.fetch_binance_open_interest_stats(),
            self.fetch_bybit_linear_tickers(),
            self.fetch_okx_funding_rates(tracked_coins),
            self.fetch_okx_liquidations(tracked_coins),
            self.fetch_dydx_markets(),
            self.fetch_coinglass_liquidations(),
            return_exceptions=True,
        )

        # Handle potential gather exceptions safely
        if isinstance(binance_indexes, Exception):
            logger.warning("Error gathering binance indexes: %s", binance_indexes)
            binance_indexes = {}
        if isinstance(binance_ratios, Exception):
            logger.warning("Error gathering binance ratios: %s", binance_ratios)
            binance_ratios = {}
        if isinstance(binance_oi_stats, Exception):
            logger.warning("Error gathering binance OI stats: %s", binance_oi_stats)
            binance_oi_stats = (0.0, 0.0)
        if isinstance(bybit_tickers, Exception):
            logger.warning("Error gathering bybit tickers: %s", bybit_tickers)
            bybit_tickers = {}
            total_bybit_oi = 0.0
        if isinstance(okx_rates, Exception):
            logger.warning("Error gathering okx rates: %s", okx_rates)
            okx_rates = {}
        if isinstance(okx_liquidations, Exception):
            logger.warning("Error gathering okx liquidations: %s", okx_liquidations)
            okx_liquidations = {
                "1h": LiquidationStats(timeframe="1h"),
                "4h": LiquidationStats(timeframe="4h"),
                "24h": LiquidationStats(timeframe="24h"),
            }
        if isinstance(dydx_markets, Exception):
            logger.warning("Error gathering dydx markets: %s", dydx_markets)
            dydx_markets = {}
        if isinstance(coinglass_stats, Exception) or coinglass_stats is None:
            coinglass_stats = None

        # Build funding rate entries for each coin
        funding_entries: list[FundingRateEntry] = []
        total_open_interest_usd = total_bybit_oi

        for coin in tracked_coins:
            display_pair = f"{coin}/USDT"
            b_sym = f"{coin}USDT"
            dydx_sym = f"{coin}-USD"

            # Binance rate & prices
            b_data = binance_indexes.get(b_sym, {})
            b_rate = (
                float(b_data["lastFundingRate"])
                if b_data and "lastFundingRate" in b_data and b_data["lastFundingRate"] is not None
                else None
            )
            mark_px = float(b_data["markPrice"]) if b_data and "markPrice" in b_data else None
            idx_px = float(b_data["indexPrice"]) if b_data and "indexPrice" in b_data else None
            nft_raw = b_data.get("nextFundingTime")
            next_ft = (
                datetime.fromtimestamp(int(nft_raw) / 1000, tz=timezone.utc)
                if nft_raw
                else None
            )

            # Bybit rate & open interest
            bybit_data = bybit_tickers.get(b_sym, {})
            bybit_rate_raw = bybit_data.get("fundingRate")
            bybit_rate = float(bybit_rate_raw) if bybit_rate_raw not in (None, "") else None
            bybit_oi = float(bybit_data.get("openInterestValue") or 0.0)

            # OKX rate
            okx_rate = okx_rates.get(coin)

            # dYdX rate
            dydx_data = dydx_markets.get(dydx_sym, {})
            dydx_rate_raw = dydx_data.get("nextFundingRate")
            dydx_rate = float(dydx_rate_raw) if dydx_rate_raw not in (None, "") else None

            # Long/Short ratio
            long_ratio, short_ratio = binance_ratios.get(b_sym, (None, None))

            entry = FundingRateEntry(
                coin=display_pair,
                symbol=coin,
                binance_rate=b_rate,
                bybit_rate=bybit_rate,
                okx_rate=okx_rate,
                dydx_rate=dydx_rate,
                long_account_ratio=long_ratio,
                short_account_ratio=short_ratio,
                open_interest_usd=bybit_oi if bybit_oi > 0 else None,
                mark_price=mark_px,
                index_price=idx_px,
                next_funding_time=next_ft,
            )
            funding_entries.append(entry)

        # Binance BTC OI & 24h % change
        binance_btc_oi, oi_24h_pct = binance_oi_stats
        total_open_interest_usd += binance_btc_oi

        oi_summary = OpenInterestSummary(
            total_open_interest_usd=total_open_interest_usd,
            change_24h_pct=oi_24h_pct,
            bybit_oi_usd=total_bybit_oi,
            binance_oi_usd=binance_btc_oi,
        )

        # Liquidations
        l24 = coinglass_stats if coinglass_stats else okx_liquidations.get("24h", LiquidationStats(timeframe="24h"))

        return DerivativesSnapshot(
            open_interest=oi_summary,
            liquidations_24h=l24,
            liquidations_by_tf=okx_liquidations,
            funding_rates=funding_entries,
            timestamp=datetime.now(),
        )
