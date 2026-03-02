"""Color system and styling constants for the terminal UI.

Design philosophy: neutral grey chrome, color reserved exclusively for
data meaning.  Borders group — they never attract attention.  The data
is loud; the chrome is invisible.
"""

from rich import box
from rich.theme import Theme

# ── Box styles ──────────────────────────────────────────────────────
BOX_DEFAULT = box.ROUNDED       # all panels
BOX_TABLE = box.SIMPLE_HEAVY    # tables (horizontal rules only)

# ── Border colors ───────────────────────────────────────────────────
BORDER_DIM = "grey27"
BORDER_ACTIVE = "cornflower_blue"

# ── Background layers (darkest → lightest) ──────────────────────────
BG_BASE = "grey3"
BG_SURFACE = "grey11"
BG_ELEVATED = "grey15"
BG_SELECTED = "grey19"

# ── Theme definition ────────────────────────────────────────────────
CRYPTOSCOPE_THEME = Theme(
    {
        # App chrome
        "header.bar": f"bold white on {BG_SURFACE}",
        "header.brand": "bold cornflower_blue",
        "header.clock": "grey70",

        # Ticker tape
        "ticker.symbol": "bold white",
        "ticker.price": "bright_white",
        "ticker.up": "bold green",
        "ticker.down": "bold red",
        "ticker.sep": "grey27",

        # Tables
        "table.header": "bold grey70",
        "table.rank": "grey50",
        "table.symbol": "bold bright_white",
        "table.name": "grey62",
        "table.price": "bold bright_white",

        # Price movement (semantic)
        "price.up": "bold green",
        "price.down": "bold red",
        "price.neutral": "grey50",

        # Panels / chrome
        "border": "grey27",
        "border.active": "cornflower_blue",
        "panel.title": "bold grey70",
        "panel.subtitle": "grey42",

        # Navigation
        "nav.tab": f"grey50 on {BG_SURFACE}",
        "nav.tab.active": f"bold bright_white on {BG_SELECTED}",
        "nav.key": "bold cornflower_blue",
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
        "muted": "grey42",
        "accent": "cornflower_blue",
        "accent2": "medium_purple1",
    }
)
