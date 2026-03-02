"""Color system and styling constants for the terminal UI.

Design philosophy: neutral grey chrome, color reserved exclusively for
data meaning.  Borders group — they never attract attention.  The data
is loud; the chrome is invisible.
"""

from __future__ import annotations

from rich import box
from rich.theme import Theme

# ── Box styles ──────────────────────────────────────────────────────
BOX_DEFAULT = box.ROUNDED       # all panels
BOX_TABLE = box.SIMPLE_HEAVY    # tables (horizontal rules only)

# ── Border colors (mutable — set by apply_theme) ───────────────────
BORDER_DIM = "grey27"
BORDER_ACTIVE = "cornflower_blue"

# ── Background layers (mutable — set by apply_theme) ────────────────
BG_BASE = "grey3"
BG_SURFACE = "grey11"
BG_ELEVATED = "grey15"
BG_SELECTED = "grey19"


# ── Theme presets ──────────────────────────────────────────────────

def _build_theme(
    *,
    bg_base: str,
    bg_surface: str,
    bg_elevated: str,
    bg_selected: str,
    border_dim: str,
    border_active: str,
    accent: str,
    accent2: str,
    text_primary: str = "bold bright_white",
    text_secondary: str = "white",
    text_tertiary: str = "grey70",
    text_muted: str = "grey42",
    up: str = "bold green",
    down: str = "bold red",
) -> dict:
    """Build a theme style dict from color parameters."""
    return {
        # App chrome
        "header.bar": f"bold white on {bg_surface}",
        "header.brand": f"bold {accent}",
        "header.clock": text_tertiary,

        # Ticker tape
        "ticker.symbol": "bold white",
        "ticker.price": "bright_white",
        "ticker.up": up,
        "ticker.down": down,
        "ticker.sep": border_dim,

        # Tables
        "table.header": f"bold {text_tertiary}",
        "table.rank": "grey50",
        "table.symbol": text_primary,
        "table.name": "grey62",
        "table.price": text_primary,

        # Price movement (semantic)
        "price.up": up,
        "price.down": down,
        "price.neutral": "grey50",

        # Panels / chrome
        "border": border_dim,
        "border.active": border_active,
        "panel.title": f"bold {text_tertiary}",
        "panel.subtitle": text_muted,

        # Navigation
        "nav.tab": f"grey50 on {bg_surface}",
        "nav.tab.active": f"bold bright_white on {bg_selected}",
        "nav.key": f"bold {accent}",
        "nav.action": "grey62",

        # Status
        "status.ok": "green",
        "status.warn": "orange1",
        "status.error": "red",
        "status.dot.ok": "bold green",
        "status.dot.error": "bold red",

        # Sentiment
        "sentiment.bullish": "green",
        "sentiment.bearish": "red",
        "sentiment.neutral": "grey50",

        # Sparkline
        "spark.up": "green",
        "spark.down": "red",

        # General
        "muted": text_muted,
        "accent": accent,
        "accent2": accent2,
    }


# ── Preset definitions ────────────────────────────────────────────

THEME_PRESETS: dict[str, dict] = {
    "default": {
        "bg_base": "grey3",
        "bg_surface": "grey11",
        "bg_elevated": "grey15",
        "bg_selected": "grey19",
        "border_dim": "grey27",
        "border_active": "cornflower_blue",
        "accent": "cornflower_blue",
        "accent2": "medium_purple1",
    },
    "midnight": {
        "bg_base": "grey3",
        "bg_surface": "grey7",
        "bg_elevated": "grey11",
        "bg_selected": "grey15",
        "border_dim": "dark_blue",
        "border_active": "dodger_blue2",
        "accent": "dodger_blue2",
        "accent2": "deep_sky_blue1",
    },
    "emerald": {
        "bg_base": "grey3",
        "bg_surface": "grey11",
        "bg_elevated": "grey15",
        "bg_selected": "grey19",
        "border_dim": "grey27",
        "border_active": "dark_sea_green",
        "accent": "dark_sea_green",
        "accent2": "spring_green3",
        "up": "bold spring_green3",
        "down": "bold indian_red1",
    },
    "amber": {
        "bg_base": "grey3",
        "bg_surface": "grey11",
        "bg_elevated": "grey15",
        "bg_selected": "grey19",
        "border_dim": "grey27",
        "border_active": "dark_orange",
        "accent": "dark_orange",
        "accent2": "gold1",
        "up": "bold green",
        "down": "bold orange_red1",
    },
    "rose": {
        "bg_base": "grey3",
        "bg_surface": "grey11",
        "bg_elevated": "grey15",
        "bg_selected": "grey19",
        "border_dim": "grey27",
        "border_active": "hot_pink",
        "accent": "hot_pink",
        "accent2": "deep_pink2",
    },
}


def get_theme(name: str) -> Theme:
    """Build a Rich Theme from a preset name."""
    preset = THEME_PRESETS.get(name, THEME_PRESETS["default"])
    styles = _build_theme(**preset)
    return Theme(styles)


def apply_theme(name: str) -> Theme:
    """Apply a theme preset, updating the module-level color constants.

    Returns the Rich Theme object for use with Console.
    """
    global BORDER_DIM, BORDER_ACTIVE, BG_BASE, BG_SURFACE, BG_ELEVATED, BG_SELECTED

    preset = THEME_PRESETS.get(name, THEME_PRESETS["default"])
    BG_BASE = preset["bg_base"]
    BG_SURFACE = preset["bg_surface"]
    BG_ELEVATED = preset["bg_elevated"]
    BG_SELECTED = preset["bg_selected"]
    BORDER_DIM = preset["border_dim"]
    BORDER_ACTIVE = preset["border_active"]

    return get_theme(name)


# ── Default theme (built at import time) ──────────────────────────
CRYPTOSCOPE_THEME = get_theme("default")
