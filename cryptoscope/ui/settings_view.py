"""In-terminal settings page — navigate and edit config without leaving the app."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cryptoscope.config import save_config
from cryptoscope.ui.panels import VIEW_SETTINGS, build_footer, build_header
from cryptoscope.ui.themes import (
    THEME_PRESETS,
    apply_theme,
)

# Import these as functions so we always get the current value after theme switch
import cryptoscope.ui.themes as _themes


def _border_dim() -> str:
    return _themes.BORDER_DIM


def _border_active() -> str:
    return _themes.BORDER_ACTIVE


def _bg_selected() -> str:
    return _themes.BG_SELECTED


def _bg_surface() -> str:
    return _themes.BG_SURFACE


def _box_default():
    return _themes.BOX_DEFAULT


# ── Setting type descriptors ──────────────────────────────────────


class SettingType(Enum):
    TEXT = auto()
    SELECT = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    LIST = auto()


@dataclass
class SettingDef:
    key: str
    label: str
    type: SettingType
    section: str
    choices: list[str] = field(default_factory=list)
    min_val: int = 0
    max_val: int = 999
    masked: bool = False


# ── Category definitions ──────────────────────────────────────────

CATEGORIES: list[tuple[str, list[SettingDef]]] = [
    (
        "General",
        [
            SettingDef(
                "currency", "Currency", SettingType.SELECT, "general",
                choices=["usd", "eur", "gbp", "jpy", "btc"],
            ),
            SettingDef(
                "refresh_interval", "Refresh (sec)", SettingType.NUMBER, "general",
                min_val=5, max_val=300,
            ),
            SettingDef(
                "theme", "Theme", SettingType.SELECT, "general",
                choices=list(THEME_PRESETS.keys()),
            ),
        ],
    ),
    (
        "Watchlist",
        [
            SettingDef("coins", "Coins", SettingType.LIST, "watchlist"),
        ],
    ),
    (
        "API Keys",
        [
            SettingDef("coingecko", "CoinGecko", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("coinmarketcap", "CoinMarketCap", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("cryptocompare", "CryptoCompare", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("cryptopanic", "CryptoPanic", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("lunarcrush", "LunarCrush", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("glassnode", "Glassnode", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("etherscan", "Etherscan", SettingType.TEXT, "api_keys", masked=True),
            SettingDef("fred", "FRED", SettingType.TEXT, "api_keys", masked=True),
        ],
    ),
    (
        "Display",
        [
            SettingDef("show_volume", "Show Volume", SettingType.BOOLEAN, "display"),
            SettingDef("show_market_cap", "Show Market Cap", SettingType.BOOLEAN, "display"),
            SettingDef("show_1h_change", "Show 1h Change", SettingType.BOOLEAN, "display"),
            SettingDef("show_24h_change", "Show 24h Change", SettingType.BOOLEAN, "display"),
            SettingDef("show_7d_change", "Show 7d Change", SettingType.BOOLEAN, "display"),
            SettingDef(
                "max_watchlist_rows", "Max Rows", SettingType.NUMBER, "display",
                min_val=5, max_val=100,
            ),
        ],
    ),
]


# ── Focus targets ─────────────────────────────────────────────────


class Focus(Enum):
    SIDEBAR = auto()
    FIELDS = auto()


# ── Settings view ─────────────────────────────────────────────────


class SettingsView:
    """In-terminal settings page with Tab focus switching.

    - Tab switches focus between the category sidebar and the fields panel.
    - UP/DOWN navigates within the focused panel.
    - Enter/Space activates a field when the fields panel is focused.
    - Escape exits settings (from sidebar) or returns focus to sidebar (from fields).
    """

    NAV_SIDEBAR_KEYS: list[tuple[str, str]] = [
        ("Esc", "back"),
        ("↑↓", "category"),
        ("Tab", "fields"),
    ]

    NAV_FIELDS_KEYS: list[tuple[str, str]] = [
        ("Esc", "sidebar"),
        ("↑↓", "nav"),
        ("Tab", "sidebar"),
        ("Enter", "edit"),
    ]

    EDIT_KEYS: list[tuple[str, str]] = [
        ("Esc", "cancel"),
        ("Enter", "confirm"),
    ]

    def __init__(self) -> None:
        self.config: dict = {}
        self.tickers: list = []
        self.last_update = None
        self.status: str = "OK"

        # Navigation
        self.focus = Focus.SIDEBAR
        self.category_index: int = 0
        self.field_index: int = 0

        # Edit mode
        self.editing: bool = False
        self.edit_buffer: str = ""
        self.edit_cursor: int = 0

        # Theme change callback (set by app.py)
        self.on_theme_change = None

    def load(self, config: dict) -> None:
        """Load a fresh copy of config when entering settings."""
        self.config = copy.deepcopy(config)
        self.focus = Focus.SIDEBAR
        self.category_index = 0
        self.field_index = 0
        self.editing = False
        self.edit_buffer = ""

    # ── Config access ─────────────────────────────────────────────

    @property
    def _current_category(self) -> tuple[str, list[SettingDef]]:
        return CATEGORIES[self.category_index]

    @property
    def _current_fields(self) -> list[SettingDef]:
        return self._current_category[1]

    @property
    def _current_field(self) -> SettingDef:
        return self._current_fields[self.field_index]

    def _get_value(self, setting: SettingDef) -> Any:
        return self.config.get(setting.section, {}).get(setting.key)

    def _set_value(self, setting: SettingDef, value: Any) -> None:
        if setting.section not in self.config:
            self.config[setting.section] = {}
        self.config[setting.section][setting.key] = value

    def _save(self) -> None:
        save_config(self.config)

    # ── Key handling ──────────────────────────────────────────────

    def handle_key(self, key: str) -> str | None:
        """Handle a keypress. Returns ``'exit'`` to leave settings."""
        if self.editing:
            return self._handle_edit_key(key)
        if self.focus == Focus.SIDEBAR:
            return self._handle_sidebar_key(key)
        return self._handle_fields_key(key)

    def _handle_sidebar_key(self, key: str) -> str | None:
        if key == "ESCAPE":
            return "exit"
        if key == "UP":
            self.category_index = max(0, self.category_index - 1)
            self.field_index = 0
        elif key == "DOWN":
            self.category_index = min(len(CATEGORIES) - 1, self.category_index + 1)
            self.field_index = 0
        elif key in ("\t", "TAB", "ENTER", "RIGHT"):
            self.focus = Focus.FIELDS
            self.field_index = 0
        return None

    def _handle_fields_key(self, key: str) -> str | None:
        fields = self._current_fields

        if key in ("ESCAPE", "LEFT"):
            self.focus = Focus.SIDEBAR
            return None
        if key in ("\t", "TAB"):
            self.focus = Focus.SIDEBAR
            return None

        if key == "UP":
            self.field_index = max(0, self.field_index - 1)
        elif key == "DOWN":
            self.field_index = min(len(fields) - 1, self.field_index + 1)
        elif key in ("ENTER", " "):
            setting = self._current_field
            if setting.type == SettingType.BOOLEAN:
                self._set_value(setting, not self._get_value(setting))
                self._save()
            elif setting.type == SettingType.SELECT:
                self._cycle_select(setting, 1)
            elif setting.type in (SettingType.TEXT, SettingType.NUMBER, SettingType.LIST):
                self._enter_edit_mode(setting)
        elif key == "RIGHT":
            setting = self._current_field
            if setting.type == SettingType.SELECT:
                self._cycle_select(setting, 1)
        return None

    def _handle_edit_key(self, key: str) -> str | None:
        if key == "ESCAPE":
            self.editing = False
            self.edit_buffer = ""
        elif key == "ENTER":
            self._apply_edit(self._current_field)
            self.editing = False
            self.edit_buffer = ""
        elif key == "BACKSPACE":
            if self.edit_cursor > 0:
                self.edit_buffer = (
                    self.edit_buffer[: self.edit_cursor - 1]
                    + self.edit_buffer[self.edit_cursor :]
                )
                self.edit_cursor -= 1
        elif key == "LEFT":
            self.edit_cursor = max(0, self.edit_cursor - 1)
        elif key == "RIGHT":
            self.edit_cursor = min(len(self.edit_buffer), self.edit_cursor + 1)
        elif len(key) == 1 and key.isprintable():
            self.edit_buffer = (
                self.edit_buffer[: self.edit_cursor]
                + key
                + self.edit_buffer[self.edit_cursor :]
            )
            self.edit_cursor += 1

        return None

    # ── Helpers ───────────────────────────────────────────────────

    def _enter_edit_mode(self, setting: SettingDef) -> None:
        self.editing = True
        current = self._get_value(setting)
        if setting.type == SettingType.LIST and isinstance(current, list):
            self.edit_buffer = ", ".join(current)
        else:
            self.edit_buffer = str(current) if current else ""
        self.edit_cursor = len(self.edit_buffer)

    def _cycle_select(self, setting: SettingDef, direction: int) -> None:
        current = self._get_value(setting)
        choices = setting.choices
        try:
            idx = choices.index(current)
        except ValueError:
            idx = 0
        new_idx = (idx + direction) % len(choices)
        new_val = choices[new_idx]
        self._set_value(setting, new_val)
        self._save()

        # Live-apply theme changes
        if setting.key == "theme" and setting.section == "general":
            if self.on_theme_change:
                self.on_theme_change(new_val)

    def _apply_edit(self, setting: SettingDef) -> None:
        val = self.edit_buffer.strip()
        if setting.type == SettingType.NUMBER:
            try:
                num = int(val)
                num = max(setting.min_val, min(setting.max_val, num))
                self._set_value(setting, num)
            except ValueError:
                return
        elif setting.type == SettingType.LIST:
            items = [x.strip().lower() for x in val.split(",") if x.strip()]
            self._set_value(setting, items)
        else:
            self._set_value(setting, val)
        self._save()

    # ── Rendering ─────────────────────────────────────────────────

    def build(self) -> Layout:
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["header"].update(build_header(self.tickers))

        # Body: sidebar + fields
        body = Layout()
        body.split_row(
            Layout(name="sidebar", size=22),
            Layout(name="fields"),
        )
        body["sidebar"].update(self._build_category_sidebar())
        body["fields"].update(self._build_fields_panel())
        layout["body"].update(body)

        # Pick keybindings based on current state
        if self.editing:
            keys = self.EDIT_KEYS
        elif self.focus == Focus.SIDEBAR:
            keys = self.NAV_SIDEBAR_KEYS
        else:
            keys = self.NAV_FIELDS_KEYS

        layout["footer"].update(
            build_footer(
                active_view=VIEW_SETTINGS,
                last_update=self.last_update,
                status=self.status,
                keybindings=keys,
            )
        )

        return layout

    def _build_category_sidebar(self) -> Panel:
        sidebar_focused = self.focus == Focus.SIDEBAR

        text = Text()
        for i, (name, _) in enumerate(CATEGORIES):
            is_active = i == self.category_index
            if is_active and sidebar_focused:
                text.append(f"\n  \u25b8 {name} ", style=f"bold bright_white on {_bg_selected()}")
            elif is_active:
                text.append(f"\n  \u25b8 {name} ", style="bold bright_white")
            else:
                text.append(f"\n    {name} ", style="grey62")
        text.append("\n")

        return Panel(
            text,
            title="[bold grey70]Categories[/bold grey70]",
            box=_box_default(),
            border_style=_border_active() if sidebar_focused else _border_dim(),
        )

    def _build_fields_panel(self) -> Panel:
        cat_name, fields = self._current_category
        fields_focused = self.focus == Focus.FIELDS

        table = Table(
            show_header=True,
            header_style="bold grey70",
            box=None,
            expand=True,
            pad_edge=True,
        )
        table.add_column("Setting", min_width=18)
        table.add_column("Value", ratio=1)
        table.add_column("", width=12, justify="right")

        for i, setting in enumerate(fields):
            is_selected = i == self.field_index and fields_focused
            value = self._get_value(setting)
            row_style = f"bold on {_bg_selected()}" if is_selected else ""

            # Label
            label = Text(
                setting.label,
                style="bold bright_white" if is_selected else "grey70",
            )

            # Value
            if is_selected and self.editing:
                val_text = self._render_edit_buffer()
            elif setting.masked and value:
                dots = min(len(str(value)), 20)
                val_text = Text("\u25cf" * dots, style="grey50")
            elif setting.type == SettingType.BOOLEAN:
                on = bool(value)
                icon = "\u25cf" if on else "\u25cb"
                val_text = Text(
                    f"{icon} {'ON' if on else 'OFF'}",
                    style="green" if on else "grey42",
                )
            elif setting.type == SettingType.SELECT:
                # Show current value with arrows indicating cyclable
                val_text = Text()
                if is_selected:
                    val_text.append("\u25c0 ", style="grey42")
                val_text.append(str(value), style=_border_active())
                if is_selected:
                    val_text.append(" \u25b6", style="grey42")
            elif setting.type == SettingType.LIST and isinstance(value, list):
                val_text = Text(", ".join(value), style="bright_white")
            else:
                val_text = Text(str(value) if value else "\u2014", style="bright_white")

            # Hint
            hints = {
                SettingType.BOOLEAN: "Enter/Space",
                SettingType.SELECT: "Enter/\u2192",
                SettingType.TEXT: "Enter",
                SettingType.NUMBER: "Enter",
                SettingType.LIST: "Enter",
            }
            hint = Text(hints.get(setting.type, ""), style="grey42") if is_selected else Text("")

            table.add_row(label, val_text, hint, style=row_style)

        # Note for API keys
        if cat_name == "API Keys":
            table.add_row(
                Text(""),
                Text("Restart app for key changes to take effect", style="grey42"),
                Text(""),
            )

        # Border: active when editing or when fields panel is focused
        if self.editing:
            border = _border_active()
        elif fields_focused:
            border = _border_active()
        else:
            border = _border_dim()

        return Panel(
            table,
            title=f"[bold grey70]{cat_name}[/bold grey70]",
            box=_box_default(),
            border_style=border,
        )

    def _render_edit_buffer(self) -> Text:
        """Render edit buffer with visible cursor."""
        text = Text()
        buf = self.edit_buffer
        cursor = self.edit_cursor

        text.append(buf[:cursor], style="bright_white")
        if cursor < len(buf):
            text.append(buf[cursor], style="bold black on white")
            text.append(buf[cursor + 1 :], style="bright_white")
        else:
            text.append(" ", style="bold black on white")

        return text
