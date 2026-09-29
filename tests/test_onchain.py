"""Unit tests for On-Chain Analytics and Whale Movement Radar."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from cryptoscope.data.blockchain_com import BlockchainComProvider
from cryptoscope.data.etherscan import EtherscanProvider
from cryptoscope.data.whale_alert import WhaleAlertProvider
from cryptoscope.db import Database
from cryptoscope.models.onchain import (
    ExchangeFlow,
    GasPriceInfo,
    MempoolStats,
    WhaleTransfer,
)
from cryptoscope.ui.onchain_view import OnChainView


class TestOnChainModels(TestCase):
    """Test on-chain data models."""

    def test_gas_price_info_serialization(self) -> None:
        gp = GasPriceInfo(
            safe_low=15.0,
            standard=22.0,
            fast=30.0,
            base_fee=18.5,
            priority_fee=3.5,
            source="Etherscan",
            has_api_key=True,
            status_msg="OK",
        )
        d = gp.to_dict()
        self.assertEqual(d["safe_low"], 15.0)
        self.assertEqual(d["standard"], 22.0)
        self.assertEqual(d["fast"], 30.0)
        self.assertEqual(d["base_fee"], 18.5)
        self.assertEqual(d["priority_fee"], 3.5)
        self.assertTrue(d["has_api_key"])

        recovered = GasPriceInfo.from_dict(d)
        self.assertEqual(recovered.safe_low, gp.safe_low)
        self.assertEqual(recovered.standard, gp.standard)
        self.assertEqual(recovered.fast, gp.fast)
        self.assertEqual(recovered.base_fee, gp.base_fee)
        self.assertEqual(recovered.priority_fee, gp.priority_fee)
        self.assertEqual(recovered.has_api_key, gp.has_api_key)

    def test_mempool_stats(self) -> None:
        ms = MempoolStats(
            hashrate_eh=685.2,
            difficulty_trillion=92.4,
            difficulty_change_pct=1.8,
            difficulty_change_days=3.0,
            mempool_tx_count=142000,
            mempool_size_bytes=192937984,  # ~184 MB
        )
        self.assertAlmostEqual(ms.mempool_size_mb, 184.0, places=0)

        d = ms.to_dict()
        recovered = MempoolStats.from_dict(d)
        self.assertEqual(recovered.hashrate_eh, 685.2)
        self.assertEqual(recovered.difficulty_trillion, 92.4)
        self.assertEqual(recovered.difficulty_change_pct, 1.8)
        self.assertEqual(recovered.mempool_tx_count, 142000)

    def test_exchange_flow_classification(self) -> None:
        outflow = ExchangeFlow(
            symbol="BTC",
            net_flow=-12450.0,
        )
        self.assertTrue(outflow.is_outflow)
        self.assertFalse(outflow.is_inflow)
        self.assertIn("Outflow", outflow.resolved_classification)

        inflow = ExchangeFlow(
            symbol="ETH",
            net_flow=48200.0,
        )
        self.assertTrue(inflow.is_inflow)
        self.assertFalse(inflow.is_outflow)
        self.assertIn("Inflow", inflow.resolved_classification)

        d = outflow.to_dict()
        recovered = ExchangeFlow.from_dict(d)
        self.assertEqual(recovered.symbol, "BTC")
        self.assertEqual(recovered.net_flow, -12450.0)

    def test_whale_transfer_properties(self) -> None:
        # Inflow to exchange
        inflow = WhaleTransfer(
            timestamp=datetime.now(),
            blockchain="BTC",
            symbol="BTC",
            amount=2500.0,
            amount_usd=162500000.0,
            from_label="Unknown Wallet",
            to_label="Coinbase",
        )
        self.assertTrue(inflow.is_inflow)
        self.assertFalse(inflow.is_outflow)
        self.assertEqual(inflow.flow_color, "red")

        # Outflow from exchange
        outflow = WhaleTransfer(
            timestamp=datetime.now(),
            blockchain="ETH",
            symbol="ETH",
            amount=15000.0,
            amount_usd=39000000.0,
            from_label="Binance",
            to_label="Unknown Wallet (Cold)",
        )
        self.assertFalse(outflow.is_inflow)
        self.assertTrue(outflow.is_outflow)
        self.assertEqual(outflow.flow_color, "green")

        # Mint
        mint = WhaleTransfer(
            timestamp=datetime.now(),
            blockchain="ETH",
            symbol="USDT",
            amount=50000000.0,
            amount_usd=50000000.0,
            from_label="Tether Treasury",
            to_label="Tether Treasury",
            transfer_type="mint",
        )
        self.assertTrue(mint.is_mint)
        self.assertEqual(mint.flow_color, "cyan")

        # Between unknown wallets
        unknown = WhaleTransfer(
            timestamp=datetime.now(),
            blockchain="BTC",
            symbol="BTC",
            amount=1200.0,
            amount_usd=78000000.0,
            from_label="Unknown Wallet",
            to_label="Unknown Wallet",
        )
        self.assertFalse(unknown.is_inflow)
        self.assertFalse(unknown.is_outflow)
        self.assertFalse(unknown.is_mint)
        self.assertEqual(unknown.flow_color, "bright_white")


class TestOnChainProviders(IsolatedAsyncioTestCase):
    """Test on-chain data providers with mocked API responses."""

    async def test_blockchain_com_fetch_network_stats(self) -> None:
        provider = BlockchainComProvider()
        mock_stats = {
            "hash_rate": 685200000000.0,  # 685.2 EH/s
            "difficulty": 92400000000000.0,  # 92.4 T
            "n_blocks_total": 969170,
            "nextretarget": 969600,
            "minutes_between_blocks": 9.8,
        }

        with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_stats
            with patch.object(provider.mempool_client, "get", new_callable=AsyncMock) as mock_mp:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"count": 142000, "vsize": 192937984}
                mock_mp.return_value = mock_resp

                stats = await provider.fetch_network_stats()

                self.assertAlmostEqual(stats.hashrate_eh, 685.2, places=1)
                self.assertAlmostEqual(stats.difficulty_trillion, 92.4, places=1)
                self.assertEqual(stats.mempool_tx_count, 142000)
                self.assertGreater(stats.mempool_size_bytes, 100_000_000)

        await provider.close()

    async def test_etherscan_gas_oracle(self) -> None:
        provider = EtherscanProvider(api_key="TEST_KEY")
        mock_data = {
            "status": "1",
            "message": "OK",
            "result": {
                "SafeGasPrice": "8",
                "ProposeGasPrice": "12",
                "FastGasPrice": "18",
                "suggestBaseFee": "9.4",
            },
        }

        with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_data
            gas_info = await provider.fetch_gas_oracle()

            self.assertEqual(gas_info.safe_low, 8.0)
            self.assertEqual(gas_info.standard, 12.0)
            self.assertEqual(gas_info.fast, 18.0)
            self.assertEqual(gas_info.base_fee, 9.4)
            self.assertTrue(gas_info.has_api_key)

        await provider.close()

    async def test_etherscan_missing_key_fallback(self) -> None:
        # Without API key, should gracefully handle and use fallback
        provider = EtherscanProvider(api_key="")

        with patch.object(provider, "_get", new_callable=AsyncMock) as mock_get:
            # Simulate rate limit / missing key response
            mock_get.return_value = {"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}
            with patch.object(provider, "_fetch_gas_rpc_fallback", new_callable=AsyncMock) as mock_fallback:
                mock_fallback.return_value = GasPriceInfo(
                    safe_low=7.0,
                    standard=11.0,
                    fast=16.0,
                    base_fee=8.5,
                    priority_fee=2.5,
                    source="Public RPC",
                    has_api_key=False,
                    status_msg="RPC fallback (no Etherscan key)",
                )

                gas_info = await provider.fetch_gas_oracle()
                self.assertEqual(gas_info.safe_low, 7.0)
                self.assertFalse(gas_info.has_api_key)
                self.assertIn("no Etherscan key", gas_info.status_msg)

        await provider.close()

    async def test_whale_alert_provider_threshold_and_flows(self) -> None:
        mock_btc = MagicMock()
        mock_btc.fetch_recent_large_transactions = AsyncMock(return_value=[
            {"hash": "btctx123", "btc": 20.0, "timestamp": datetime.now()},
            {"hash": "btctxsmall", "btc": 0.5, "timestamp": datetime.now()},
        ])
        mock_eth = MagicMock()
        mock_eth.api_key = ""
        mock_eth.fetch_recent_large_transactions = AsyncMock(return_value=[
            WhaleTransfer(
                timestamp=datetime.now(),
                blockchain="ETH",
                symbol="ETH",
                amount=500.0,
                amount_usd=1_300_000.0,
                from_label="Unknown Wallet",
                to_label="Binance",
                tx_hash="ethtx123",
                transfer_type="transfer",
            )
        ])

        provider = WhaleAlertProvider(
            threshold_usd=1_000_000.0,
            blockchain_provider=mock_btc,
            etherscan_provider=mock_eth,
        )
        transfers = await provider.fetch_transfers(min_usd=1_000_000.0)

        self.assertGreater(len(transfers), 0)
        for t in transfers:
            self.assertGreaterEqual(t.amount_usd, 1_000_000.0)

        # Test exchange flows calculation
        flows = provider.calculate_exchange_flows(transfers)
        symbols = [f.symbol for f in flows]
        self.assertIn("BTC", symbols)
        self.assertIn("ETH", symbols)

        btc_flow = next(f for f in flows if f.symbol == "BTC")
        eth_flow = next(f for f in flows if f.symbol == "ETH")
        self.assertIsNotNone(btc_flow.resolved_classification)
        self.assertIsNotNone(eth_flow.resolved_classification)

        await provider.close()


class TestOnChainUI(TestCase):
    """Test OnChainView UI rendering and key actions."""

    def test_onchain_view_build(self) -> None:
        view = OnChainView()
        view.gas_price = GasPriceInfo(
            safe_low=8.0, standard=12.0, fast=18.0, base_fee=9.4, priority_fee=2.1, has_api_key=False
        )
        view.mempool_stats = MempoolStats(
            hashrate_eh=685.2,
            difficulty_trillion=92.4,
            difficulty_change_pct=1.8,
            difficulty_change_days=3.0,
            mempool_tx_count=142000,
            mempool_size_bytes=184 * 1024 * 1024,
        )
        view.exchange_flows = [
            ExchangeFlow(symbol="BTC", net_flow=-12450.0, classification="Outflow / Bullish Accumulation"),
            ExchangeFlow(symbol="ETH", net_flow=48200.0, classification="Inflow / Potential Sell Pressure"),
        ]
        view.whale_transfers = [
            WhaleTransfer(
                timestamp=datetime.now(),
                blockchain="BTC",
                symbol="BTC",
                amount=2500.0,
                amount_usd=162500000.0,
                from_label="Unknown Wallet",
                to_label="Coinbase",
            ),
            WhaleTransfer(
                timestamp=datetime.now(),
                blockchain="ETH",
                symbol="ETH",
                amount=15000.0,
                amount_usd=39000000.0,
                from_label="Binance",
                to_label="Unknown Wallet (Cold)",
            ),
        ]

        layout = view.build()
        self.assertIsNotNone(layout)
        self.assertIsNotNone(layout["header"])
        self.assertIsNotNone(layout["body"])
        self.assertIsNotNone(layout["footer"])

    def test_toggle_threshold(self) -> None:
        view = OnChainView()
        self.assertEqual(view.whale_threshold_usd, 1_000_000.0)

        view.toggle_threshold()
        self.assertEqual(view.whale_threshold_usd, 5_000_000.0)

        view.toggle_threshold()
        self.assertEqual(view.whale_threshold_usd, 10_000_000.0)

        view.toggle_threshold()
        self.assertEqual(view.whale_threshold_usd, 1_000_000.0)

    def test_scroll_whale_feed(self) -> None:
        view = OnChainView()
        view.whale_transfers = [
            WhaleTransfer(
                timestamp=datetime.now(),
                blockchain="BTC",
                symbol="BTC",
                amount=100.0,
                amount_usd=8_000_000.0,
                from_label="Unknown",
                to_label="Unknown",
            )
            for _ in range(25)
        ]
        self.assertEqual(view.whale_scroll_offset, 0)

        view.scroll_whale_feed(1)
        self.assertEqual(view.whale_scroll_offset, 1)

        view.scroll_whale_feed(-1)
        self.assertEqual(view.whale_scroll_offset, 0)

        # Cannot scroll below 0
        view.scroll_whale_feed(-5)
        self.assertEqual(view.whale_scroll_offset, 0)


class TestOnChainDatabaseCaching(IsolatedAsyncioTestCase):
    """Test SQLite caching for gas prices and mempool stats."""

    async def test_gas_and_mempool_caching(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_cryptoscope.db"
            db = Database(db_path=db_path)
            await db.connect()

            # 1. Test gas price caching (15 seconds TTL)
            gp = GasPriceInfo(safe_low=10.0, standard=15.0, fast=20.0, base_fee=12.0)
            await db.cache_set("onchain_gas_price", gp.to_dict(), ttl_seconds=15)

            cached_gp_data = await db.cache_get("onchain_gas_price")
            self.assertIsNotNone(cached_gp_data)
            recovered_gp = GasPriceInfo.from_dict(cached_gp_data)
            self.assertEqual(recovered_gp.safe_low, 10.0)
            self.assertEqual(recovered_gp.standard, 15.0)

            # 2. Test mempool stats caching (60 seconds TTL)
            ms = MempoolStats(
                hashrate_eh=700.0,
                difficulty_trillion=95.0,
                difficulty_change_pct=2.1,
                difficulty_change_days=4.0,
                mempool_tx_count=135000,
                mempool_size_bytes=150000000,
            )
            await db.cache_set("onchain_mempool_stats", ms.to_dict(), ttl_seconds=60)

            cached_ms_data = await db.cache_get("onchain_mempool_stats")
            self.assertIsNotNone(cached_ms_data)
            recovered_ms = MempoolStats.from_dict(cached_ms_data)
            self.assertEqual(recovered_ms.hashrate_eh, 700.0)
            self.assertEqual(recovered_ms.difficulty_trillion, 95.0)

            await db.close()


class TestAppOnChainIntegration(IsolatedAsyncioTestCase):
    """Test CryptoScopeApp On-Chain view mode and key navigation."""

    async def test_app_onchain_keybindings(self) -> None:
        from cryptoscope.app import CryptoScopeApp, ViewMode

        with patch("cryptoscope.app.ensure_config") as mock_cfg:
            mock_cfg.return_value = {
                "general": {"currency": "usd", "refresh_interval": 10, "theme": "default"},
                "watchlist": {"coins": ["bitcoin", "ethereum"]},
                "api_keys": {"coingecko": "", "etherscan": ""},
                "onchain": {"etherscan_api_key": "", "whale_threshold_usd": 1_000_000},
                "display": {"show_volume": True, "show_market_cap": True, "max_watchlist_rows": 25},
            }
            app = CryptoScopeApp()

            self.assertEqual(app.view_mode, ViewMode.WATCHLIST)
            self.assertIsNotNone(app.onchain_view)
            self.assertIsNotNone(app.blockchain_com)
            self.assertIsNotNone(app.etherscan)
            self.assertIsNotNone(app.whale_alert)

            # Test F4 key switches to ONCHAIN view
            with patch.object(app, "_fetch_and_render_onchain", new_callable=AsyncMock):
                await app._handle_key("F4")
                self.assertEqual(app.view_mode, ViewMode.ONCHAIN)

            # Test onchain view key actions
            # 'w' toggles whale threshold
            init_thresh = app.onchain_view.whale_threshold_usd
            await app._handle_key("w")
            self.assertNotEqual(app.onchain_view.whale_threshold_usd, init_thresh)

            # 'UP' / 'DOWN' scroll
            app.onchain_view.whale_transfers = [
                WhaleTransfer(
                    timestamp=datetime.now(),
                    blockchain="BTC",
                    symbol="BTC",
                    amount=500.0,
                    amount_usd=40_000_000.0,
                )
                for _ in range(20)
            ]
            await app._handle_key("DOWN")
            self.assertEqual(app.onchain_view.whale_scroll_offset, 1)
            await app._handle_key("UP")
            self.assertEqual(app.onchain_view.whale_scroll_offset, 0)

            # '1' returns to WATCHLIST
            await app._handle_key("1")
            self.assertEqual(app.view_mode, ViewMode.WATCHLIST)

            # '4' from WATCHLIST switches to ONCHAIN
            with patch.object(app, "_fetch_and_render_onchain", new_callable=AsyncMock):
                await app._handle_key("4")
                self.assertEqual(app.view_mode, ViewMode.ONCHAIN)

            # 'ESCAPE' returns to WATCHLIST
            await app._handle_key("ESCAPE")
            self.assertEqual(app.view_mode, ViewMode.WATCHLIST)
