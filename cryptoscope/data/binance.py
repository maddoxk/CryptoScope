"""Binance data provider — REST and WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

import websockets

from cryptoscope.data.base import DataProvider
from cryptoscope.models.price import OHLCV, OrderBook, OrderBookEntry, Ticker

logger = logging.getLogger(__name__)

BINANCE_REST = "https://api.binance.com/api/v3"
BINANCE_WS = "wss://stream.binance.com:9443/ws"


class BinanceProvider(DataProvider):
    """Binance public API provider (no auth required)."""

    def __init__(self) -> None:
        super().__init__(base_url=BINANCE_REST, calls_per_minute=1200)
        self._ws_task: asyncio.Task | None = None
        self._ws_callbacks: dict[str, Callable] = {}

    async def fetch_tickers(self, coin_ids: list[str]) -> list[Ticker]:
        """Fetch 24h ticker stats for given symbols.

        Note: coin_ids here should be Binance symbols like BTCUSDT, ETHUSDT.
        """
        tickers = []
        for symbol in coin_ids:
            try:
                data = await self._get("/ticker/24hr", params={"symbol": symbol.upper()})
                tickers.append(self._parse_ticker(data))
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", symbol, e)
        return tickers

    async def fetch_ticker_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        data = await self._get("/ticker/price", params={"symbol": symbol.upper()})
        return float(data["price"])

    async def fetch_klines(
        self,
        symbol: str,
        interval: str = "1d",
        limit: int = 100,
    ) -> list[OHLCV]:
        """Fetch kline/candlestick data.

        interval: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M
        """
        data = await self._get(
            "/klines",
            params={
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
            },
        )
        return [
            OHLCV(
                timestamp=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
            for k in data
        ]

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> OrderBook:
        """Fetch order book depth and return an OrderBook model."""
        data = await self._get(
            "/depth",
            params={"symbol": symbol.upper(), "limit": limit},
        )
        return OrderBook(
            symbol=symbol.upper(),
            bids=[OrderBookEntry(price=float(b[0]), quantity=float(b[1])) for b in data.get("bids", [])],
            asks=[OrderBookEntry(price=float(a[0]), quantity=float(a[1])) for a in data.get("asks", [])],
        )

    async def start_price_stream(
        self,
        symbols: list[str],
        callback: Callable[[str, float], Any],
    ) -> None:
        """Start WebSocket stream for real-time mini-ticker updates."""
        streams = "/".join(f"{s.lower()}@miniTicker" for s in symbols)
        url = f"{BINANCE_WS}/{streams}"

        async def _ws_loop() -> None:
            while True:
                try:
                    async with websockets.connect(url) as ws:
                        logger.info("WebSocket connected for %d symbols", len(symbols))
                        async for msg in ws:
                            data = json.loads(msg)
                            symbol = data.get("s", "")
                            price = float(data.get("c", 0))
                            await callback(symbol, price)
                except websockets.ConnectionClosed:
                    logger.warning("WebSocket disconnected, reconnecting in 5s...")
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error("WebSocket error: %s", e)
                    await asyncio.sleep(5)

        self._ws_task = asyncio.create_task(_ws_loop())

    async def stop_price_stream(self) -> None:
        """Stop the WebSocket stream."""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None

    def _parse_ticker(self, data: dict[str, Any]) -> Ticker:
        symbol = data.get("symbol", "")
        return Ticker(
            id=symbol,
            symbol=symbol,
            name=symbol,
            price_usd=float(data.get("lastPrice", 0)),
            volume_24h=float(data.get("quoteVolume", 0)),
            change_24h=float(data.get("priceChangePercent", 0)),
            last_updated=datetime.now(),
        )
