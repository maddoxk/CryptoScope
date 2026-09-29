"""On-Chain Analytics and Whale Movement Radar view."""

from __future__ import annotations

from datetime import datetime

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cryptoscope.models.onchain import (
    ExchangeFlow,
    GasPriceInfo,
    MempoolStats,
    WhaleTransfer,
)
from cryptoscope.ui.panels import VIEW_ONCHAIN, build_footer, build_header
import cryptoscope.ui.themes as _themes


class OnChainView:
    """Manages the on-chain dashboard state and rendering."""

    ONCHAIN_KEYS: list[tuple[str, str]] = [
        ("Esc", "back"),
        ("↑↓", "scroll"),
        ("w", "threshold"),
        ("g", "refresh gas"),
        ("r", "refresh all"),
        ("F7", "settings"),
        ("q", "quit"),
    ]

    THRESHOLDS: list[float] = [1_000_000.0, 5_000_000.0, 10_000_000.0]

    def __init__(self) -> None:
        self.gas_price: GasPriceInfo | None = None
        self.mempool_stats: MempoolStats | None = None
        self.exchange_flows: list[ExchangeFlow] = []
        self.whale_transfers: list[WhaleTransfer] = []
        self.whale_threshold_usd: float = 1_000_000.0
        self.whale_scroll_offset: int = 0
        self.tickers = []  # for header ticker tape
        self.last_update: datetime | None = None
        self.status: str = "OK"
        self.status_msg: str = ""

    def toggle_threshold(self) -> None:
        """Cycle the minimum whale alert threshold ($1M -> $5M -> $10M)."""
        try:
            curr_idx = self.THRESHOLDS.index(self.whale_threshold_usd)
            next_idx = (curr_idx + 1) % len(self.THRESHOLDS)
        except ValueError:
            next_idx = 0
        self.whale_threshold_usd = self.THRESHOLDS[next_idx]
        self.whale_scroll_offset = 0

    def scroll_whale_feed(self, direction: int) -> None:
        """Scroll the whale alert feed up or down."""
        filtered = self.get_filtered_transfers()
        max_offset = max(0, len(filtered) - 10)
        self.whale_scroll_offset = max(0, min(max_offset, self.whale_scroll_offset + direction))

    def get_filtered_transfers(self) -> list[WhaleTransfer]:
        """Return transactions meeting or exceeding the current USD threshold."""
        return [t for t in self.whale_transfers if t.amount_usd >= self.whale_threshold_usd]

    def build(self) -> Layout:
        """Build the complete On-Chain Radar dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(build_header(self.tickers))

        body = Layout()
        body.split_column(
            Layout(name="network", size=6),
            Layout(name="flows", size=5),
            Layout(name="whales", ratio=1),
        )

        body["network"].update(self._build_network_panel())
        body["flows"].update(self._build_flows_panel())
        body["whales"].update(self._build_whale_feed_panel())

        layout["body"].update(body)

        layout["footer"].update(
            build_footer(
                active_view=VIEW_ONCHAIN,
                last_update=self.last_update,
                status=self.status,
                keybindings=self.ONCHAIN_KEYS,
                error_msg=self.status_msg,
            )
        )

        return layout

    def _build_network_panel(self) -> Panel:
        """Network Health: BTC Hashrate/Difficulty/Mempool & ETH Gas tiers."""
        text = Text()

        # Row 1: BTC telemetry
        ms = self.mempool_stats
        if ms and (ms.hashrate_eh > 0 or ms.mempool_tx_count > 0):
            text.append("BTC Hashrate: ", style="bold bright_white")
            text.append(f"{ms.hashrate_eh:.1f} EH/s" if ms.hashrate_eh > 0 else "N/A", style="bold cyan")
            text.append("  |  ", style="grey42")
            text.append("Difficulty: ", style="bold bright_white")
            diff_sign = "+" if ms.difficulty_change_pct >= 0 else ""
            diff_style = "green" if ms.difficulty_change_pct >= 0 else "red"
            text.append(f"{ms.difficulty_trillion:.1f} T " if ms.difficulty_trillion > 0 else "N/A ", style="bright_white")
            if ms.difficulty_change_pct != 0.0:
                text.append(f"({diff_sign}{ms.difficulty_change_pct:.1f}% in {ms.difficulty_change_days:.0f}d)", style=diff_style)
            text.append("  |  ", style="grey42")
            text.append("Mempool: ", style="bold bright_white")
            tx_k = ms.mempool_tx_count / 1000
            mb = ms.mempool_size_mb
            text.append(f"{tx_k:.0f}k txs ({mb:.0f} MB)", style="yellow")
        else:
            text.append("Bitcoin Telemetry: [dim]Connecting to live mempool and block streams...[/dim]")
        text.append("\n")

        # Row 2: ETH gas tiers
        gp = self.gas_price
        if gp and gp.standard > 0:
            text.append("ETH Gas: ", style="bold bright_white")
            text.append("Low ", style="grey62")
            text.append(f"{gp.safe_low:.0f} gwei", style="green")
            text.append(" | ", style="grey42")
            text.append("Med ", style="grey62")
            text.append(f"{gp.standard:.0f} gwei", style="yellow")
            text.append(" | ", style="grey42")
            text.append("High ", style="grey62")
            text.append(f"{gp.fast:.0f} gwei", style="red")
            text.append(" | ", style="grey42")
            text.append("Base Fee: ", style="grey62")
            text.append(f"{gp.base_fee:.1f} gwei", style="bright_white")
            text.append(" | ", style="grey42")
            text.append("Priority: ", style="grey62")
            text.append(f"{gp.priority_fee:.1f} gwei", style="bright_white")

            if not gp.has_api_key:
                text.append("  [dim yellow](Public RPC fallback — configure key in F7 Settings)[/dim yellow]")
            elif gp.status_msg:
                text.append(f"  [dim grey62]({gp.status_msg})[/dim grey62]")
        else:
            text.append("Ethereum Gas: [dim]Connecting to live public Ethereum RPC...[/dim]")

        return Panel(
            text,
            title="[bold grey70]Network Health: Bitcoin & Ethereum[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )

    def _build_flows_panel(self) -> Panel:
        """Exchange Net Flows (24h): Inflow (sell pressure) vs Outflow (accumulation)."""
        text = Text()

        flows = self.exchange_flows
        if not flows or all(f.net_flow == 0.0 for f in flows):
            text.append("Exchange Net Flows: [dim]Monitoring live mempool and block transactions (no exchange flow bias detected in current window)[/dim]")
        else:
            for i, flow in enumerate(flows):
                if i > 0:
                    text.append("\n")
                symbol = flow.symbol
                net = flow.net_flow
                sign = "+" if net > 0 else ""
                arrow = "▲" if net > 0 else "▼" if net < 0 else "━"
                color = "red" if net > 0 else "green" if net < 0 else "grey62"
                classification = flow.resolved_classification

                text.append(f"{symbol}:  ", style="bold bright_white")
                text.append(f"{arrow} {sign}{net:,.2f} {symbol} ", style=f"bold {color}")
                text.append(f"({classification})", style=f"{color}")

        return Panel(
            text,
            title="[bold grey70]Exchange Net Flows (24h)[/bold grey70]",
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )

    def _build_whale_feed_panel(self) -> Panel:
        """Live Whale Alert Feed (> threshold) with color-coded flow indicators."""
        threshold_fmt = f"${int(self.whale_threshold_usd):,} USD"
        title = f"[bold grey70]Live Whale Alert Feed (> {threshold_fmt})[/bold grey70]"

        filtered = self.get_filtered_transfers()
        if not filtered:
            return Panel(
                Text(f"Scanning live Bitcoin mempool & Ethereum blocks...\nNo whale transactions observed above {threshold_fmt} in recent blocks.\nPress 'w' to cycle threshold ($1M / $5M / $10M) or 'r' to refresh.", style="grey50", justify="center"),
                title=title,
                box=_themes.BOX_DEFAULT,
                border_style=_themes.BORDER_DIM,
            )

        visible = filtered[self.whale_scroll_offset : self.whale_scroll_offset + 10]
        text = Text()

        for t in visible:
            text.append(f"{t.formatted_time} ", style="grey50")
            text.append("🐳 ", style="bright_white")
            text.append(f"{t.amount:,.0f} {t.symbol} (${t.amount_usd:,.0f}) ", style="bold bright_white")

            if t.is_mint:
                text.append("minted at ", style="grey62")
                text.append(t.to_label, style="bold cyan")
                text.append(" [MINT]", style="cyan")
            elif t.is_inflow:
                text.append(f"transferred from {t.from_label} to ", style="grey62")
                text.append(t.to_label, style="bold red")
                text.append(" [INFLOW / SELL]", style="red")
            elif t.is_outflow:
                text.append(f"transferred from {t.from_label} to ", style="grey62")
                text.append(t.to_label, style="bold green")
                text.append(" [OUTFLOW / ACCUM]", style="green")
            else:
                if t.from_label.lower() == "unknown wallet" and t.to_label.lower() == "unknown wallet":
                    text.append("transferred between unknown wallets", style="grey62")
                else:
                    text.append(f"transferred from {t.from_label} to {t.to_label}", style="grey70")
                text.append(" [TRANSFER]", style="grey50")

            text.append("\n")

        # Scroll / status footer inside panel
        total = len(filtered)
        if total > 0:
            start = self.whale_scroll_offset + 1
            end = min(total, self.whale_scroll_offset + len(visible))
            text.append(f"\n{start}-{end} of {total}  |  ↑↓ scroll  |  w toggle threshold  |  g refresh gas", style="grey42")

        return Panel(
            text,
            title=title,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
        )
