"""Unit tests for Derivatives Dashboard & Cross-Exchange Funding Rate Heatmap."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from cryptoscope.app import CryptoScopeApp, ViewMode
from cryptoscope.data.derivatives import DEFAULT_COINS, DerivativesProvider
from cryptoscope.models.derivatives import (
    DerivativesSnapshot,
    FundingRateEntry,
    LiquidationStats,
    OpenInterestSummary,
)
from cryptoscope.ui.derivatives_view import DerivativesView
from cryptoscope.ui.panels import VIEW_DERIVATIVES, build_footer


class TestDerivativesModels(TestCase):
    """Test derivatives dataclass models and serialization."""

    def test_funding_rate_entry_serialization(self) -> None:
        entry = FundingRateEntry(
            coin="BTC/USDT",
            symbol="BTC",
            binance_rate=0.0001,
            bybit_rate=0.000098,
            okx_rate=0.000102,
            dydx_rate=0.000091,
            long_account_ratio=0.58,
            short_account_ratio=0.42,
            open_interest_usd=7_800_000_000.0,
            mark_price=83000.0,
            index_price=83050.0,
            next_funding_time=datetime(2026, 9, 29, 20, 0, 0, tzinfo=timezone.utc),
        )
        d = entry.to_dict()
        self.assertEqual(d["coin"], "BTC/USDT")
        self.assertEqual(d["symbol"], "BTC")
        self.assertEqual(d["binance_rate"], 0.0001)
        self.assertEqual(d["bybit_rate"], 0.000098)
        self.assertEqual(d["long_account_ratio"], 0.58)

        recovered = FundingRateEntry.from_dict(d)
        self.assertEqual(recovered.coin, entry.coin)
        self.assertEqual(recovered.symbol, entry.symbol)
        self.assertAlmostEqual(recovered.binance_rate, 0.0001)
        self.assertAlmostEqual(recovered.bybit_rate, 0.000098)
        self.assertAlmostEqual(recovered.long_account_ratio, 0.58)
        self.assertEqual(recovered.mark_price, 83000.0)

    def test_average_funding_rate(self) -> None:
        # All available
        entry = FundingRateEntry(
            coin="ETH/USDT",
            symbol="ETH",
            binance_rate=0.0001,
            bybit_rate=0.0002,
            okx_rate=0.0003,
            dydx_rate=0.0004,
        )
        self.assertAlmostEqual(entry.average_funding_rate, 0.00025)

        # Some None
        entry2 = FundingRateEntry(
            coin="SOL/USDT",
            symbol="SOL",
            binance_rate=0.0002,
            bybit_rate=None,
            okx_rate=0.0004,
            dydx_rate=None,
        )
        self.assertAlmostEqual(entry2.average_funding_rate, 0.0003)

        # All None
        entry3 = FundingRateEntry(coin="DOGE/USDT", symbol="DOGE")
        self.assertIsNone(entry3.average_funding_rate)

    def test_open_interest_summary_serialization(self) -> None:
        oi = OpenInterestSummary(
            total_open_interest_usd=38_400_000_000.0,
            change_24h_pct=4.2,
            bybit_oi_usd=13_000_000_000.0,
            binance_oi_usd=25_400_000_000.0,
        )
        d = oi.to_dict()
        self.assertEqual(d["total_open_interest_usd"], 38_400_000_000.0)
        self.assertEqual(d["change_24h_pct"], 4.2)

        recovered = OpenInterestSummary.from_dict(d)
        self.assertEqual(recovered.total_open_interest_usd, 38_400_000_000.0)
        self.assertEqual(recovered.change_24h_pct, 4.2)

    def test_liquidation_stats(self) -> None:
        stats = LiquidationStats(
            timeframe="4h",
            long_liquidations_usd=48_200_000.0,
            short_liquidations_usd=11_400_000.0,
        )
        self.assertEqual(stats.total_liquidations_usd, 59_600_000.0)
        d = stats.to_dict()
        self.assertEqual(d["timeframe"], "4h")
        recovered = LiquidationStats.from_dict(d)
        self.assertEqual(recovered.total_liquidations_usd, 59_600_000.0)

    def test_derivatives_snapshot_serialization(self) -> None:
        snap = DerivativesSnapshot(
            open_interest=OpenInterestSummary(total_open_interest_usd=10_000.0, change_24h_pct=1.5),
            liquidations_24h=LiquidationStats(timeframe="24h", long_liquidations_usd=100.0, short_liquidations_usd=50.0),
            liquidations_by_tf={
                "1h": LiquidationStats(timeframe="1h", long_liquidations_usd=10.0, short_liquidations_usd=5.0),
            },
            funding_rates=[
                FundingRateEntry(coin="BTC/USDT", symbol="BTC", binance_rate=0.0001),
            ],
        )
        d = snap.to_dict()
        recovered = DerivativesSnapshot.from_dict(d)
        self.assertEqual(recovered.open_interest.total_open_interest_usd, 10_000.0)
        self.assertEqual(recovered.liquidations_24h.long_liquidations_usd, 100.0)
        self.assertEqual(len(recovered.funding_rates), 1)
        self.assertEqual(recovered.funding_rates[0].coin, "BTC/USDT")


class TestDerivativesView(TestCase):
    """Test DerivativesView formatting, rendering, and interactions."""

    def setUp(self) -> None:
        self.view = DerivativesView()
        self.view.snapshot = DerivativesSnapshot(
            open_interest=OpenInterestSummary(
                total_open_interest_usd=38_400_000_000.0,
                change_24h_pct=4.2,
            ),
            liquidations_24h=LiquidationStats(
                timeframe="24h",
                long_liquidations_usd=122_000_000.0,
                short_liquidations_usd=62_000_000.0,
            ),
            liquidations_by_tf={
                "1h": LiquidationStats(timeframe="1h", long_liquidations_usd=12_000_000.0, short_liquidations_usd=3_000_000.0),
                "4h": LiquidationStats(timeframe="4h", long_liquidations_usd=48_200_000.0, short_liquidations_usd=11_400_000.0),
                "24h": LiquidationStats(timeframe="24h", long_liquidations_usd=122_000_000.0, short_liquidations_usd=62_000_000.0),
            },
            funding_rates=[
                FundingRateEntry(
                    coin="BTC/USDT", symbol="BTC",
                    binance_rate=0.0001, bybit_rate=0.000098, okx_rate=0.000102, dydx_rate=0.000091,
                    long_account_ratio=0.58, open_interest_usd=8_000_000_000.0,
                ),
                FundingRateEntry(
                    coin="ETH/USDT", symbol="ETH",
                    binance_rate=0.000125, bybit_rate=0.000130, okx_rate=0.000118, dydx_rate=0.000110,
                    long_account_ratio=0.52, open_interest_usd=4_000_000_000.0,
                ),
                FundingRateEntry(
                    coin="SOL/USDT", symbol="SOL",
                    binance_rate=0.000240, bybit_rate=0.000255, okx_rate=0.000238, dydx_rate=0.000210,
                    long_account_ratio=0.67, open_interest_usd=2_000_000_000.0,
                ),
                FundingRateEntry(
                    coin="DOGE/USDT", symbol="DOGE",
                    binance_rate=-0.000050, bybit_rate=-0.000042, okx_rate=-0.000061, dydx_rate=-0.000035,
                    long_account_ratio=0.41, open_interest_usd=500_000_000.0,
                ),
            ],
        )

    def test_format_funding_rate(self) -> None:
        # Extreme positive funding (>= +0.0150%) has 🔥
        hot_text = DerivativesView.format_funding_rate(0.000240)
        self.assertIn("🔥", hot_text.plain)
        self.assertIn("+0.0240%", hot_text.plain)

        # Negative funding (< 0.0%) has ❄️
        cold_text = DerivativesView.format_funding_rate(-0.000050)
        self.assertIn("❄️", cold_text.plain)
        self.assertIn("-0.0050%", cold_text.plain)

        # Moderate positive funding
        mod_text = DerivativesView.format_funding_rate(0.000100)
        self.assertNotIn("🔥", mod_text.plain)
        self.assertNotIn("❄️", mod_text.plain)
        self.assertIn("+0.0100%", mod_text.plain)

        # None / N/A
        na_text = DerivativesView.format_funding_rate(None)
        self.assertIn("N/A", na_text.plain)

    def test_format_long_short_bar(self) -> None:
        bar58 = DerivativesView.format_long_short_bar(0.58)
        self.assertIn("58%", bar58.plain)
        self.assertIn("██████", bar58.plain)

        bar67 = DerivativesView.format_long_short_bar(0.67)
        self.assertIn("67%", bar67.plain)

        bar41 = DerivativesView.format_long_short_bar(0.41)
        self.assertIn("41%", bar41.plain)

        na_bar = DerivativesView.format_long_short_bar(None)
        self.assertIn("N/A", na_bar.plain)

    def test_cycle_sort(self) -> None:
        self.assertEqual(self.view.sort_mode, "default")
        self.view.cycle_sort()
        self.assertEqual(self.view.sort_mode, "funding_desc")
        self.view.cycle_sort()
        self.assertEqual(self.view.sort_mode, "funding_asc")
        self.view.cycle_sort()
        self.assertEqual(self.view.sort_mode, "oi_desc")
        self.view.cycle_sort()
        self.assertEqual(self.view.sort_mode, "long_short_desc")
        self.view.cycle_sort()
        self.assertEqual(self.view.sort_mode, "default")

    def test_sorting_entries(self) -> None:
        # Highest funding rate first (SOL should be first)
        self.view.sort_mode = "funding_desc"
        entries = self.view.get_sorted_entries()
        self.assertEqual(entries[0].symbol, "SOL")

        # Lowest funding rate first (DOGE should be first)
        self.view.sort_mode = "funding_asc"
        entries = self.view.get_sorted_entries()
        self.assertEqual(entries[0].symbol, "DOGE")

        # Highest OI first (BTC should be first)
        self.view.sort_mode = "oi_desc"
        entries = self.view.get_sorted_entries()
        self.assertEqual(entries[0].symbol, "BTC")

        # Highest L/S ratio first (SOL at 67% should be first)
        self.view.sort_mode = "long_short_desc"
        entries = self.view.get_sorted_entries()
        self.assertEqual(entries[0].symbol, "SOL")

    def test_cycle_timeframe(self) -> None:
        self.assertEqual(self.view.timeframe, "4h")
        self.view.cycle_timeframe()
        self.assertEqual(self.view.timeframe, "24h")
        self.view.cycle_timeframe()
        self.assertEqual(self.view.timeframe, "1h")
        self.view.cycle_timeframe()
        self.assertEqual(self.view.timeframe, "4h")

    def test_select_row(self) -> None:
        self.assertEqual(self.view.selected_row, 0)
        self.view.select_row(1)
        self.assertEqual(self.view.selected_row, 1)
        self.view.select_row(10)
        self.assertEqual(self.view.selected_row, 3)  # clamped to max index 3
        self.view.select_row(-10)
        self.assertEqual(self.view.selected_row, 0)  # clamped to 0

    def test_build_layout(self) -> None:
        layout = self.view.build()
        self.assertIsNotNone(layout)
        self.assertIsNotNone(layout["header"])
        self.assertIsNotNone(layout["body"])
        self.assertIsNotNone(layout["footer"])

    def test_footer_tab_active(self) -> None:
        footer = build_footer(active_view=VIEW_DERIVATIVES)
        self.assertIsNotNone(footer)


class TestDerivativesProvider(IsolatedAsyncioTestCase):
    """Test DerivativesProvider with mock HTTP responses."""

    async def asyncSetUp(self) -> None:
        self.provider = DerivativesProvider()

    async def asyncTearDown(self) -> None:
        await self.provider.close()

    async def test_fetch_binance_premium_indexes(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "symbol": "BTCUSDT",
                "markPrice": "82950.0",
                "indexPrice": "82990.0",
                "lastFundingRate": "0.000100",
                "nextFundingTime": 1790697600000,
            },
            {
                "symbol": "ETHUSDT",
                "markPrice": "2670.0",
                "indexPrice": "2672.0",
                "lastFundingRate": "0.000125",
                "nextFundingTime": 1790697600000,
            },
        ]
        with patch.object(self.provider.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            indexes = await self.provider.fetch_binance_premium_indexes()
            self.assertIn("BTCUSDT", indexes)
            self.assertEqual(indexes["BTCUSDT"]["markPrice"], "82950.0")
            self.assertEqual(indexes["BTCUSDT"]["lastFundingRate"], "0.000100")

    async def test_fetch_binance_long_short_ratios(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"symbol": "BTCUSDT", "longAccount": "0.582", "shortAccount": "0.418"}
        ]
        with patch.object(self.provider.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            ratios = await self.provider.fetch_binance_long_short_ratios(["BTCUSDT"])
            self.assertIn("BTCUSDT", ratios)
            long_acc, short_acc = ratios["BTCUSDT"]
            self.assertAlmostEqual(long_acc, 0.582)
            self.assertAlmostEqual(short_acc, 0.418)

    async def test_fetch_bybit_linear_tickers(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "list": [
                    {
                        "symbol": "BTCUSDT",
                        "fundingRate": "0.000098",
                        "openInterestValue": "4500000000.0",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "fundingRate": "0.000130",
                        "openInterestValue": "2500000000.0",
                    },
                ]
            }
        }
        with patch.object(self.provider.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            tickers, total_oi = await self.provider.fetch_bybit_linear_tickers()
            self.assertIn("BTCUSDT", tickers)
            self.assertEqual(tickers["BTCUSDT"]["fundingRate"], "0.000098")
            self.assertEqual(total_oi, 7_000_000_000.0)

    async def test_fetch_okx_funding_rates(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "code": "0",
            "data": [{"fundingRate": "0.000102", "fundingTime": "1790697600000"}],
        }
        with patch.object(self.provider.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            rates = await self.provider.fetch_okx_funding_rates(["BTC"])
            self.assertIn("BTC", rates)
            self.assertAlmostEqual(rates["BTC"], 0.000102)

    async def test_fetch_dydx_markets(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "markets": {
                "BTC-USD": {
                    "ticker": "BTC-USD",
                    "nextFundingRate": "0.000091",
                    "oraclePrice": "82950.0",
                }
            }
        }
        with patch.object(self.provider.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            markets = await self.provider.fetch_dydx_markets()
            self.assertIn("BTC-USD", markets)
            self.assertEqual(markets["BTC-USD"]["nextFundingRate"], "0.000091")

    async def test_fetch_derivatives_snapshot_graceful_failures(self) -> None:
        # Ensure that if all endpoints raise an exception, snapshot returns empty structure without crash
        with patch.object(self.provider.client, "get", side_effect=Exception("Network error")):
            snap = await self.provider.fetch_derivatives_snapshot(["BTC", "ETH"], force_refresh=True)
            self.assertIsNotNone(snap)
            self.assertEqual(len(snap.funding_rates), 2)
            # Rates should cleanly be None (displayed as N/A in UI)
            self.assertIsNone(snap.funding_rates[0].binance_rate)
            self.assertIsNone(snap.funding_rates[0].bybit_rate)
            self.assertIsNone(snap.funding_rates[0].okx_rate)
            self.assertIsNone(snap.funding_rates[0].dydx_rate)


class TestAppDerivativesIntegration(IsolatedAsyncioTestCase):
    """Test full application controller navigation and key handling for Derivatives view."""

    async def asyncSetUp(self) -> None:
        with patch("cryptoscope.app.ensure_config") as mock_cfg:
            mock_cfg.return_value = {
                "general": {"currency": "usd", "refresh_interval": 10, "theme": "default"},
                "watchlist": {"coins": ["bitcoin", "ethereum"]},
                "api_keys": {},
                "onchain": {},
                "derivatives": {"liquidation_timeframe": "4h", "sort_by": "default"},
            }
            self.app = CryptoScopeApp()

    async def asyncTearDown(self) -> None:
        await self.app.db.close()
        await self.app.derivatives.close()

    async def test_f5_switches_to_derivatives_view(self) -> None:
        self.assertEqual(self.app.view_mode, ViewMode.WATCHLIST)
        with patch.object(self.app, "_fetch_and_render_derivatives", new_callable=AsyncMock):
            await self.app._handle_key("F5")
            self.assertEqual(self.app.view_mode, ViewMode.DERIVATIVES)

    async def test_key_5_switches_to_derivatives_view(self) -> None:
        self.assertEqual(self.app.view_mode, ViewMode.WATCHLIST)
        with patch.object(self.app, "_fetch_and_render_derivatives", new_callable=AsyncMock):
            await self.app._handle_key("5")
            self.assertEqual(self.app.view_mode, ViewMode.DERIVATIVES)

    async def test_derivatives_keys_handling(self) -> None:
        self.app.view_mode = ViewMode.DERIVATIVES
        dv = self.app.derivatives_view

        # Sort toggle
        self.assertEqual(dv.sort_mode, "default")
        await self.app._handle_key("s")
        self.assertEqual(dv.sort_mode, "funding_desc")

        # Timeframe toggle
        self.assertEqual(dv.timeframe, "4h")
        await self.app._handle_key("t")
        self.assertEqual(dv.timeframe, "24h")

        # Back to watchlist via Escape
        await self.app._handle_key("ESCAPE")
        self.assertEqual(self.app.view_mode, ViewMode.WATCHLIST)
