"""Rich Layout manager for the terminal UI."""

from __future__ import annotations

from datetime import datetime

from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from cryptoscope.models.price import Ticker
from cryptoscope.ui.panels import (
    VIEW_WATCHLIST,
    build_footer,
    build_header,
    build_watchlist_table,
)
import cryptoscope.ui.themes as _themes


class TerminalLayout:
    """Manages the main terminal layout."""

    WATCHLIST_KEYS: list[tuple[str, str]] = [
        ("↑↓", "nav"),
        ("Enter", "chart"),
        ("r", "refresh"),
        ("F7", "settings"),
        ("q", "quit"),
    ]

    def __init__(self) -> None:
        self.tickers: list[Ticker] = []
        self.price_history: dict[str, list[float]] = {}
        self.last_update: datetime | None = None
        self.status: str = "OK"
        self.status_msg: str = ""

    def update_tickers(self, tickers: list[Ticker]) -> None:
        """Update the ticker data."""
        self.tickers = tickers
        self.last_update = datetime.now()

    def build(self, selected_row: int = -1) -> Layout:
        """Build the complete terminal layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(build_header(self.tickers))

        if self.tickers:
            layout["body"].update(
                build_watchlist_table(
                    self.tickers,
                    selected_row=selected_row,
                    price_history=self.price_history,
                )
            )
        else:
            layout["body"].update(
                Panel(
                    Text("Loading market data...", style="grey42", justify="center"),
                    box=_themes.BOX_DEFAULT,
                    border_style=_themes.BORDER_DIM,
                )
            )

        layout["footer"].update(
            build_footer(
                active_view=VIEW_WATCHLIST,
                last_update=self.last_update,
                status=self.status,
                keybindings=self.WATCHLIST_KEYS,
                error_msg=self.status_msg,
            )
        )

        return layout
