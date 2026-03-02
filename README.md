<p align="center">
  <img src="https://img.shields.io/badge/version-1.4.000-cornflowerblue?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey?style=flat-square" alt="Platform">
</p>

<h1 align="center">CryptoScope</h1>

<p align="center">
  <strong>A Bloomberg-style terminal for cryptocurrency analysis.</strong><br>
  Real-time prices, technical charts, and sentiment data — all in your terminal.
</p>

---

## Features

**Live Watchlist** — Track prices, volume, market cap, and percent changes (1h/24h/7d) with sparkline history and auto-refresh.

**Technical Analysis** — Candlestick charts with SMA, EMA, Bollinger Bands, RSI, and MACD across multiple timeframes (1H, 4H, 1D, 1W). Zoom and toggle indicators on the fly. Binance klines provide real volume data with automatic CoinGecko fallback.

**Order Book** — Live bid/ask depth panel with spread calculation, powered by Binance. Toggle with `o` in chart view.

**Pair Finder** — Browse all CoinGecko coins by market cap, search by name/symbol, and add/remove coins from your watchlist without leaving the terminal.

**Sentiment Dashboard** — Fear & Greed Index, crypto news feed, social engagement metrics (LunarCrush), Reddit sentiment analysis, and Google Trends — aggregated in a single view.

**Settings Panel** — Edit configuration in-app: currency, refresh interval, theme, watchlist, API keys, and display preferences. Changes apply live.

**Theme System** — Multiple color themes with live switching. Includes default, ocean, ember, matrix, and more.

**Keyboard-Driven** — Navigate entirely with keyboard shortcuts. No mouse required.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/maddoxk/CryptoScope.git
cd CryptoScope

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Run
cryptoscope
```

On first launch, a setup wizard will walk you through currency preference, watchlist, and API key configuration.

---

## Configuration

Configuration lives at `~/.cryptoscope/config.toml`. Created automatically on first run.

```toml
[general]
currency = "usd"
refresh_interval = 10
theme = "default"

[watchlist]
coins = ["bitcoin", "ethereum", "solana", "cardano", "dogecoin"]

[api_keys]
coingecko = ""
cryptopanic = ""
lunarcrush = ""
# See Data Sources below for full list
```

---

## Keybindings

### Global

| Key | Action |
|-----|--------|
| `q` | Quit |
| `F1` | Watchlist view |
| `F2` | Sentiment view |
| `F3` | Pair finder |
| `F7` | Settings |
| `r` | Force refresh |

### Watchlist

| Key | Action |
|-----|--------|
| `UP` / `DOWN` | Navigate coins |
| `ENTER` | Open chart for selected coin |

### Chart View

| Key | Action |
|-----|--------|
| `ESC` / `BACKSPACE` | Back to watchlist |
| `LEFT` / `RIGHT` | Cycle timeframe (1H / 4H / 1D / 1W) |
| `+` / `-` | Zoom in / out |
| `s` | Toggle SMA subplot |
| `e` | Toggle EMA |
| `b` | Toggle Bollinger Bands |
| `i` | Toggle RSI |
| `m` | Toggle MACD |
| `o` | Toggle order book |

### Pair Finder

| Key | Action |
|-----|--------|
| `ESC` | Back to previous view |
| `UP` / `DOWN` | Navigate coins |
| `LEFT` / `RIGHT` | Previous / next page |
| `/` | Search by name/symbol |
| `a` | Add selected coin to watchlist |
| `d` | Remove selected coin from watchlist |

### Sentiment View

| Key | Action |
|-----|--------|
| `ESC` / `BACKSPACE` | Back to watchlist |
| `UP` / `DOWN` | Scroll news feed |

### Settings

| Key | Action |
|-----|--------|
| `ESC` | Back (from sidebar) / sidebar (from fields) |
| `UP` / `DOWN` | Navigate categories or fields |
| `Tab` | Switch focus between sidebar and fields |
| `Enter` / `Space` | Edit selected field |

---

## Data Sources

All providers use free-tier APIs. API keys are optional but recommended for higher rate limits.

| Provider | Data | Auth Required |
|----------|------|:---:|
| [CoinGecko](https://www.coingecko.com/en/api) | Prices, market cap, OHLCV, coin details | Optional |
| [Binance](https://binance-docs.github.io/apidocs/) | Real-time ticker, klines, order book | No |
| [Alternative.me](https://alternative.me/crypto/fear-and-greed-index/) | Fear & Greed Index | No |
| [CryptoPanic](https://cryptopanic.com/developers/api/) | Aggregated crypto news with sentiment | Optional |
| [LunarCrush](https://lunarcrush.com/developers/api) | Social mentions, engagement, galaxy score | Optional |
| [Reddit](https://www.reddit.com) | Subreddit post volume and keyword sentiment | No |
| [Google Trends](https://trends.google.com) | Search interest and spike detection | No |

---

## Project Structure

```
cryptoscope/
├── main.py                 # Entry point
├── app.py                  # Application orchestrator (render, data, input loops)
├── config.py               # TOML config loader and first-run wizard
├── db.py                   # SQLite cache, watchlists, price snapshots
├── data/
│   ├── base.py             # Abstract provider + token-bucket rate limiter
│   ├── coingecko.py        # Prices, market data, OHLCV, coin list
│   ├── binance.py          # REST + WebSocket ticker, klines, order book
│   ├── symbol_map.py       # CoinGecko ID → Binance symbol mapping
│   ├── fear_greed.py       # Fear & Greed Index
│   ├── cryptopanic.py      # News aggregation
│   ├── lunarcrush.py       # Social engagement metrics
│   ├── reddit.py           # Subreddit sentiment analysis
│   └── trends.py           # Google Trends interest data
├── models/
│   ├── price.py            # Ticker, OHLCV, OrderBook dataclasses
│   └── sentiment.py        # FearGreed, NewsItem, SocialMetrics, TrendingTopic
├── ui/
│   ├── layout.py           # Watchlist view layout
│   ├── panels.py           # Header, footer, watchlist table, sparklines
│   ├── chart_view.py       # Candlestick chart detail view + order book
│   ├── sentiment_view.py   # Sentiment dashboard (FNG, news, social, trends)
│   ├── pair_finder.py      # Browse/search all coins, manage watchlist
│   ├── settings_view.py    # In-app settings editor
│   ├── input.py            # Async non-blocking key reader
│   └── themes.py           # Color system, theme presets, live switching
├── charting/
│   ├── engine.py           # plotext chart rendering (candlestick, line)
│   └── indicators.py       # SMA, EMA, RSI, MACD, Bollinger Bands, VWAP
└── utils/
    └── formatting.py       # Price, volume, and percent formatting
```

---

## Architecture

CryptoScope runs three concurrent async loops:

- **Render loop** — redraws the active view at ~30fps using [Rich](https://github.com/Textualize/rich) Live
- **Data loop** — fetches market data on a configurable interval (default 10s)
- **Input loop** — reads keystrokes without blocking

All data providers inherit from a shared base class with built-in rate limiting. API responses are cached in SQLite with TTL, and price snapshots are persisted for historical review.

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Terminal UI | [Rich](https://github.com/Textualize/rich) |
| HTTP Client | [httpx](https://www.python-httpx.org/) (async) |
| Data Processing | [pandas](https://pandas.pydata.org/) |
| Charts | [plotext](https://github.com/piccolomo/plotext) |
| Database | [aiosqlite](https://github.com/omnilib/aiosqlite) |
| WebSocket | [websockets](https://websockets.readthedocs.io/) |
| Config | TOML ([tomli](https://github.com/hukkin/tomli) / [tomli-w](https://github.com/hukkin/tomli-w)) |

---

## Requirements

- Python 3.11+
- A terminal with Unicode support (most modern terminals)
- Internet connection for live data

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check .

# Run tests
pytest
```

---

## Changelog

### v1.4.000

- **Pair Finder** (`F3`): Browse all CoinGecko coins by market cap, search by name/symbol/ID, add/remove from watchlist with `a`/`d`
- **Settings Panel** (`F7`): In-app config editor with category sidebar, inline editing for text/number/boolean/select/list fields, and live save
- **Order Book**: Live Binance bid/ask depth panel in chart view, toggled with `o`
- **Binance Klines**: Chart view now prefers Binance kline data (real volume) over CoinGecko OHLCV, with automatic fallback
- **Symbol Mapping**: CoinGecko ID to Binance trading pair mapping (`data/symbol_map.py`) for seamless cross-provider data
- **Theme System**: Multiple color presets (default, ocean, ember, matrix, etc.) with live switching from settings
- **SMA Subplot**: SMA/EMA indicators now render in a dedicated subplot below volume with color-coded lines
- **Charting Colors**: Indicator lines use a muted palette (cyan, orange, magenta, etc.) with braille markers
- **Dynamic Theming**: All UI modules reference theme constants dynamically, enabling runtime theme changes

### v1.3.005

- Initial release: watchlist, chart view, sentiment dashboard

---

## License

MIT
