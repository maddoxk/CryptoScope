"""Pair Finder view — browse and search the full CoinGecko coin list."""

from __future__ import annotations

import time

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cryptoscope.models.price import Ticker
from cryptoscope.ui.panels import VIEW_PAIRS, build_footer, build_header
import cryptoscope.ui.themes as _themes
from cryptoscope.utils.formatting import color_percent, format_large_number, format_price


PAIRS_KEYS: list[tuple[str, str]] = [
    ("Esc", "back"),
    ("↑↓", "nav"),
    ("←→", "page"),
    ("/", "search"),
    ("a", "add"),
    ("d", "remove"),
]


class PairFinderView:
    """Browse all CoinGecko coins by market cap, search, add/remove from watchlist."""

    def __init__(self) -> None:
        # Coin index — lightweight list of {id, symbol, name}
        self.coin_list: list[dict] = []

        # Current page of market data
        self.page_tickers: list[Ticker] = []

        # Pagination
        self.current_page: int = 1
        self.total_pages: int = 1
        self.per_page: int = 50
        self.total_coins: int = 0

        # Navigation
        self.selected_row: int = 0

        # Search state
        self.searching: bool = False
        self.search_buffer: str = ""
        self.search_query: str = ""        # confirmed query
        self.search_results: list[dict] = []  # filtered coin_list entries

        # Watchlist
        self.watchlist_coins: list[str] = []

        # Flash message
        self._flash_msg: str = ""
        self._flash_until: float = 0.0

        # Header ticker tape
        self.tickers: list[Ticker] = []
        self.last_update = None
        self.status: str = "OK"

    # ── Flash messages ────────────────────────────────────────────

    def flash(self, msg: str, duration: float = 2.0) -> None:
        self._flash_msg = msg
        self._flash_until = time.monotonic() + duration

    def _flash_active(self) -> str:
        if self._flash_msg and time.monotonic() < self._flash_until:
            return self._flash_msg
        return ""

    # ── Selected coin ─────────────────────────────────────────────

    @property
    def selected_coin(self) -> Ticker | None:
        if 0 <= self.selected_row < len(self.page_tickers):
            return self.page_tickers[self.selected_row]
        return None

    # ── Search helpers ────────────────────────────────────────────

    def filter_coin_list(self, query: str) -> list[dict]:
        """Client-side substring search on id/symbol/name. Caps at 250."""
        q = query.lower().strip()
        if not q:
            return []
        results = []
        for coin in self.coin_list:
            if (
                q in coin.get("id", "").lower()
                or q in coin.get("symbol", "").lower()
                or q in coin.get("name", "").lower()
            ):
                results.append(coin)
                if len(results) >= 250:
                    break
        return results

    # ── Key handling ──────────────────────────────────────────────

    def handle_key(self, key: str) -> str | None:
        """Process a keypress and return an action string for the app."""
        if self.searching:
            return self._handle_search_key(key)
        return self._handle_browse_key(key)

    def _handle_browse_key(self, key: str) -> str | None:
        n = len(self.page_tickers)

        if key == "ESCAPE" or key == "BACKSPACE":
            return "exit"

        elif key == "UP":
            if self.selected_row > 0:
                self.selected_row -= 1
            elif self.current_page > 1:
                self.current_page -= 1
                self.selected_row = self.per_page - 1
                return "fetch_page"

        elif key == "DOWN":
            if self.selected_row < n - 1:
                self.selected_row += 1
            elif self.current_page < self.total_pages:
                self.current_page += 1
                self.selected_row = 0
                return "fetch_page"

        elif key == "LEFT":
            if self.current_page > 1:
                self.current_page -= 1
                self.selected_row = 0
                return "fetch_page"

        elif key == "RIGHT":
            if self.current_page < self.total_pages:
                self.current_page += 1
                self.selected_row = 0
                return "fetch_page"

        elif key == "/":
            self.searching = True
            self.search_buffer = self.search_query  # pre-fill with last query

        elif key in ("a", "A"):
            coin = self.selected_coin
            if coin:
                return "add"

        elif key in ("d", "D"):
            coin = self.selected_coin
            if coin:
                return "remove"

        return None

    def _handle_search_key(self, key: str) -> str | None:
        if key == "ESCAPE":
            self.searching = False
            self.search_buffer = ""
            if self.search_query:
                # Clear search, go back to browse
                self.search_query = ""
                self.search_results = []
                self.current_page = 1
                self.selected_row = 0
                return "fetch_page"
            return None

        elif key == "ENTER":
            query = self.search_buffer.strip()
            self.searching = False
            if query:
                self.search_query = query
                self.search_results = self.filter_coin_list(query)
                self.current_page = 1
                self.selected_row = 0
                return "fetch_search"
            else:
                # Empty search — clear and reload browse
                self.search_query = ""
                self.search_results = []
                self.current_page = 1
                self.selected_row = 0
                return "fetch_page"

        elif key == "BACKSPACE":
            self.search_buffer = self.search_buffer[:-1]

        elif key == "DELETE":
            self.search_buffer = ""

        elif len(key) == 1 and key.isprintable():
            self.search_buffer += key

        return None

    # ── Rendering ─────────────────────────────────────────────────

    def build(self) -> Layout:
        """Build the full pair finder layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="searchbar", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(build_header(self.tickers))
        layout["searchbar"].update(self._build_search_bar())
        layout["body"].update(self._build_coin_table())
        layout["footer"].update(
            build_footer(
                active_view=VIEW_PAIRS,
                last_update=self.last_update,
                status=self.status,
                keybindings=PAIRS_KEYS,
            )
        )

        return layout

    def _build_search_bar(self) -> Panel:
        bar = Table.grid(expand=True)
        bar.add_column("left", ratio=2)
        bar.add_column("right", justify="right", ratio=1)

        # Left: search input
        left = Text()
        left.append(" Search: ", style="grey62")
        if self.searching:
            left.append(self.search_buffer or "", style="bold bright_white")
            left.append("█", style=f"bold {_themes.BORDER_ACTIVE}")
        elif self.search_query:
            left.append(self.search_query, style=f"bold {_themes.BORDER_ACTIVE}")
            left.append("  [press / to edit]", style="grey42")
        else:
            left.append("[press / to search]", style="grey42")

        # Right: flash msg OR page info
        right = Text(justify="right")
        flash = self._flash_active()
        if flash:
            right.append(flash, style=f"bold {_themes.BORDER_ACTIVE}")
        elif self.search_query:
            count = len(self.search_results)
            right.append(f"{count} results  ", style="grey62")
        else:
            right.append(
                f"Page {self.current_page}/{self.total_pages}  ({self.total_coins:,} coins)  ",
                style="grey62",
            )

        bar.add_row(left, right)

        return Panel(
            bar,
            box=_themes.BOX_DEFAULT,
            border_style=_themes.BORDER_DIM,
            style=f"on {_themes.BG_SURFACE}",
        )

    def _build_coin_table(self) -> Table:
        table = Table(
            box=_themes.BOX_TABLE,
            show_header=True,
            header_style="bold grey70",
            border_style=_themes.BORDER_DIM,
            expand=True,
            pad_edge=True,
            row_styles=["", f"on {_themes.BG_SURFACE}"],
        )

        table.add_column("", width=2, justify="center")          # star
        table.add_column("#", style="grey50", width=5, justify="right")
        table.add_column("Coin", min_width=18)
        table.add_column("Price", justify="right", min_width=12)
        table.add_column("1h", justify="right", min_width=7)
        table.add_column("24h", justify="right", min_width=7)
        table.add_column("7d", justify="right", min_width=7)
        table.add_column("Mkt Cap", justify="right", min_width=10)

        for idx, ticker in enumerate(self.page_tickers):
            row_style = f"bold on {_themes.BG_SELECTED}" if idx == self.selected_row else ""
            in_watchlist = ticker.id in self.watchlist_coins
            star = Text("★", style="gold1") if in_watchlist else Text("·", style="grey27")

            table.add_row(
                star,
                str(ticker.market_cap_rank) if ticker.market_cap_rank else "—",
                Text.assemble(
                    (ticker.symbol, "bold bright_white"),
                    " ",
                    (ticker.name, "grey62"),
                ),
                Text(format_price(ticker.price_usd), style="bold bright_white"),
                Text.from_markup(color_percent(ticker.change_1h)),
                Text.from_markup(color_percent(ticker.change_24h)),
                Text.from_markup(color_percent(ticker.change_7d)),
                format_large_number(ticker.market_cap),
                style=row_style,
            )

        if not self.page_tickers:
            table.add_row("", "", Text("Loading...", style="grey42"), "", "", "", "", "")

        return table
