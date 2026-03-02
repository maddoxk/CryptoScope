"""Number formatting and color coding utilities."""

from __future__ import annotations


def format_price(value: float) -> str:
    """Format a price value with appropriate decimal places."""
    if value >= 1_000:
        return f"${value:,.2f}"
    elif value >= 1:
        return f"${value:,.4f}"
    elif value >= 0.01:
        return f"${value:,.6f}"
    else:
        return f"${value:,.8f}"


def format_large_number(value: float) -> str:
    """Format large numbers with K/M/B/T suffixes."""
    if abs(value) >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:,.2f}T"
    elif abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    elif abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.2f}M"
    elif abs(value) >= 1_000:
        return f"${value / 1_000:,.2f}K"
    else:
        return f"${value:,.2f}"


def format_percent(value: float) -> str:
    """Format a percentage value."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def color_percent(value: float) -> str:
    """Return a Rich markup string with color coding for a percent change."""
    formatted = format_percent(value)
    if value > 0:
        return f"[green]{formatted}[/green]"
    elif value < 0:
        return f"[red]{formatted}[/red]"
    return f"[grey50]{formatted}[/grey50]"


def format_volume(value: float) -> str:
    """Format volume without dollar sign."""
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f}B"
    elif abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f}M"
    elif abs(value) >= 1_000:
        return f"{value / 1_000:,.2f}K"
    return f"{value:,.2f}"
