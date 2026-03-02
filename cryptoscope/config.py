"""Configuration management — TOML-based config with first-run wizard."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

CONFIG_DIR = Path.home() / ".cryptoscope"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "currency": "usd",
        "refresh_interval": 10,
        "theme": "default",
    },
    "watchlist": {
        "coins": ["bitcoin", "ethereum", "solana", "cardano", "dogecoin"],
    },
    "api_keys": {
        "coingecko": "",
        "coinmarketcap": "",
        "cryptocompare": "",
        "cryptopanic": "",
        "lunarcrush": "",
        "glassnode": "",
        "etherscan": "",
        "fred": "",
    },
    "display": {
        "show_volume": True,
        "show_market_cap": True,
        "show_1h_change": True,
        "show_24h_change": True,
        "show_7d_change": True,
        "max_watchlist_rows": 25,
    },
}


def load_config() -> dict[str, Any]:
    """Load config from disk, creating defaults if needed."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    with open(CONFIG_FILE, "rb") as f:
        user_config = tomllib.load(f)
    # Merge with defaults — user values take precedence
    merged = _deep_merge(DEFAULT_CONFIG, user_config)
    return merged


def save_config(config: dict[str, Any]) -> None:
    """Write config to TOML file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(config, f)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def first_run_wizard() -> dict[str, Any]:
    """Interactive setup wizard for first-time users."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm, Prompt

    console = Console()

    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to CryptoScope Terminal[/bold cyan]\n\n"
            "Let's set up your configuration.",
            title="[bold]First-Run Setup[/bold]",
            border_style="bright_blue",
        )
    )
    console.print()

    config = DEFAULT_CONFIG.copy()

    # Currency
    currency = Prompt.ask(
        "[cyan]Preferred display currency[/cyan]",
        choices=["usd", "eur", "gbp", "jpy", "btc"],
        default="usd",
    )
    config["general"]["currency"] = currency

    # Refresh interval
    interval = Prompt.ask(
        "[cyan]Refresh interval in seconds[/cyan]",
        default="10",
    )
    try:
        config["general"]["refresh_interval"] = max(5, int(interval))
    except ValueError:
        config["general"]["refresh_interval"] = 10

    # Watchlist
    console.print("\n[cyan]Default watchlist[/cyan] (comma-separated CoinGecko IDs):")
    console.print("[dim]Examples: bitcoin, ethereum, solana, cardano, dogecoin[/dim]")
    coins_input = Prompt.ask(
        "Coins",
        default="bitcoin,ethereum,solana,cardano,dogecoin",
    )
    config["watchlist"]["coins"] = [c.strip().lower() for c in coins_input.split(",") if c.strip()]

    # API Keys
    console.print("\n[cyan]API Keys[/cyan] [dim](press Enter to skip — can be added later)[/dim]")
    for key_name in ["coingecko", "coinmarketcap", "cryptocompare"]:
        value = Prompt.ask(f"  {key_name}", default="", show_default=False)
        config["api_keys"][key_name] = value

    if Confirm.ask("\n[cyan]Configure additional API keys now?[/cyan]", default=False):
        for key_name in ["cryptopanic", "lunarcrush", "glassnode", "etherscan", "fred"]:
            value = Prompt.ask(f"  {key_name}", default="", show_default=False)
            config["api_keys"][key_name] = value

    # Save
    save_config(config)
    console.print(f"\n[green]Config saved to {CONFIG_FILE}[/green]\n")

    return config


def ensure_config() -> dict[str, Any]:
    """Load config or run first-run wizard if no config exists."""
    if CONFIG_FILE.exists():
        return load_config()

    # Check if running interactively
    if sys.stdin.isatty():
        return first_run_wizard()

    # Non-interactive: save defaults
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()
