# CryptoScope Terminal: Development Plan

A Bloomberg-style terminal for cryptocurrency analysis. Built as a Python CLI application using the Rich library for terminal UI rendering.

## Tech Stack

- Language: Python 3.11+
- Terminal UI: Rich (tables, panels, live updating)
- HTTP Client: httpx (async support)
- Data Processing: pandas
- Charting: plotext (terminal-based charts)
- Config/Storage: SQLite + TOML
- Scheduling: APScheduler (background data refresh)

---

## Data Sources (All Free Tier)

### Price and Market Data
| Source | Data Provided | Auth |
|--------|--------------|------|
| CoinGecko API | Prices, volume, market cap, OHLCV for 14,000+ coins | API key (free) |
| CoinMarketCap API | Prices, rankings, global metrics, 20,000+ coins | API key (free) |
| Binance Public API | Real-time orderbook, trades, klines, ticker | None |
| CryptoCompare API | Aggregated prices, 5,700+ coins, 260,000+ pairs | API key (free) |

### Sentiment and Social
| Source | Data Provided | Auth |
|--------|--------------|------|
| Alternative.me API | Fear and Greed Index (current + historical) | None |
| CryptoPanic API | Aggregated crypto news feed with sentiment tags | API key (free) |
| LunarCrush API | Social mentions, engagement, sentiment scores | API key (free) |
| Reddit API (via PRAW) | Subreddit post volume, comment sentiment | OAuth |

### On-Chain Data
| Source | Data Provided | Auth |
|--------|--------------|------|
| Glassnode (free tier) | Active addresses, tx count, exchange flows (BTC/ETH) | API key (free) |
| Blockchain.com API | BTC mempool size, hash rate, difficulty | None |
| Etherscan API | ETH gas prices, token transfers, whale txs | API key (free) |

### Macro and Derivatives
| Source | Data Provided | Auth |
|--------|--------------|------|
| CoinGlass (web scrape) | Funding rates, open interest, liquidations | None |
| FRED API | DXY, interest rates, M2 money supply | API key (free) |
| Google Trends (pytrends) | Search interest for crypto-related terms | None |

---

## Stage 1: Core Framework and Price Engine

**Goal:** Establish project structure, config management, and live price feeds.

### Tasks for Claude Code

1. Initialize Python project with pyproject.toml, dependencies, and folder structure:
```
cryptoscope/
  __init__.py
  main.py            # Entry point, CLI arg parsing
  config.py           # TOML config loader, API key management
  db.py               # SQLite setup, schema migrations
  ui/
    __init__.py
    layout.py          # Rich Layout manager
    panels.py          # Reusable panel components
    themes.py          # Color schemes
  data/
    __init__.py
    base.py            # Abstract data provider class
    coingecko.py       # CoinGecko provider
    binance.py         # Binance WebSocket + REST
  models/
    __init__.py
    price.py           # Price, OHLCV dataclasses
  utils/
    __init__.py
    formatting.py      # Number formatting, color coding
```

2. Create config system:
   - TOML file at ~/.cryptoscope/config.toml
   - Store API keys, default watchlist, refresh intervals, preferred currency
   - First-run setup wizard in terminal

3. Implement CoinGecko provider:
   - Fetch top N coins by market cap
   - Fetch price for specific coin IDs
   - Fetch OHLCV (1d, 7d, 30d, 90d)
   - Rate limiting (30 calls/min on free tier)

4. Implement Binance provider:
   - REST: Ticker price, 24h stats, klines
   - WebSocket: Real-time price stream for watchlist pairs

5. Build main terminal layout:
   - Header bar: app name, BTC/ETH price ticker, timestamp
   - Watchlist table: coin, price, 1h%, 24h%, 7d%, volume, market cap
   - Color coding: green for positive, red for negative
   - Auto-refresh every 10 seconds

6. SQLite database:
   - Cache API responses with TTL
   - Store user watchlist
   - Store historical snapshots for offline review

### Deliverable
Running `cryptoscope` launches a live-updating terminal showing a configurable watchlist with price data, percent changes, and volume.

---

## Stage 2: Charting and Technical Indicators

**Goal:** Add terminal-based price charts and basic technical analysis.

### Tasks for Claude Code

1. Implement plotext charting module:
   - Candlestick charts (1h, 4h, 1d, 1w timeframes)
   - Line charts for price overlay
   - Volume bars below price chart
   - Responsive to terminal width/height

2. Add technical indicators (compute locally with pandas):
   - RSI (14-period)
   - MACD (12, 26, 9)
   - Bollinger Bands (20, 2)
   - Simple and Exponential Moving Averages (20, 50, 200)
   - VWAP

3. Chart navigation:
   - Keyboard shortcuts to switch timeframes
   - Zoom in/out on time axis
   - Toggle indicator overlays on/off

4. Create a detail view for a selected coin:
   - Full-width chart panel
   - Indicator values table
   - Key stats: ATH, ATL, circulating supply, max supply, market cap rank

### Deliverable
Pressing Enter on any watchlist coin opens a detail view with interactive charts and technical indicators.

---

## Stage 3: Sentiment and News Feed

**Goal:** Integrate sentiment data and a scrollable news feed.

### Tasks for Claude Code

1. Implement Alternative.me Fear and Greed provider:
   - Current index value with color-coded gauge
   - 7-day, 30-day historical chart
   - Classification label (Extreme Fear, Fear, Neutral, Greed, Extreme Greed)

2. Implement CryptoPanic news provider:
   - Fetch latest news filtered by coin
   - Display headline, source, time ago, sentiment tag (bullish/bearish/neutral)
   - Scrollable list in a Rich panel

3. Implement LunarCrush social provider:
   - Social mentions count (24h)
   - Social engagement score
   - Sentiment score (bullish %)
   - Galaxy Score (overall social health)

4. Implement Reddit sentiment:
   - Track post volume in r/cryptocurrency, r/bitcoin, r/ethereum
   - Basic keyword sentiment analysis on titles
   - Trending topics extraction

5. Implement Google Trends:
   - Search interest for "bitcoin", "ethereum", "crypto" over 7d and 90d
   - Spike detection (interest > 2x 30-day average)

6. Build sentiment dashboard panel:
   - Fear and Greed gauge
   - Social buzz score per coin
   - Trending terms list
   - News feed (most recent 20 headlines)

### Deliverable
A dedicated Sentiment tab showing fear/greed index, social metrics per coin, trending topics, and a live news feed.

---

## Stage 4: On-Chain Analytics

**Goal:** Surface blockchain-level data that signals whale activity and network health.

### Tasks for Claude Code

1. Implement Glassnode provider (free tier):
   - BTC/ETH active addresses
   - Exchange net flows (inflow vs outflow)
   - Transaction count

2. Implement Blockchain.com provider:
   - BTC hash rate and difficulty
   - Mempool size and fee estimates
   - Unconfirmed transaction count

3. Implement Etherscan provider:
   - ETH gas price (safe, standard, fast)
   - Top ERC-20 token transfers (whale alerts)
   - Contract activity for major DeFi protocols

4. Build on-chain dashboard:
   - Network health table (hash rate, difficulty, active addresses)
   - Exchange flow chart (net flow over 7d/30d)
   - Whale alert feed (large transfers > $1M)
   - Gas tracker panel

### Deliverable
An On-Chain tab displaying network fundamentals, exchange flows, whale movements, and gas prices.

---

## Stage 5: Macro Overlay and Derivatives

**Goal:** Add traditional finance context and derivatives market data.

### Tasks for Claude Code

1. Implement FRED provider:
   - DXY (US Dollar Index) with 30d chart
   - Federal Funds Rate (current + historical)
   - M2 Money Supply (monthly)
   - 10-Year Treasury Yield

2. Implement CoinGlass scraper:
   - BTC/ETH funding rates across exchanges
   - Open interest (aggregated)
   - Liquidation data (24h long vs short)
   - Long/Short ratio

3. Build macro panel:
   - DXY chart with BTC price overlay (correlation view)
   - Rate environment summary
   - Money supply trend

4. Build derivatives panel:
   - Funding rate heatmap across exchanges
   - Open interest chart
   - Liquidation bar chart (longs vs shorts)
   - Put/Call ratio (from CoinGlass)

### Deliverable
A Macro tab with traditional finance indicators and a Derivatives tab with futures/options market data.

---

## Stage 6: Alerts, Watchlists, and Portfolio

**Goal:** Personalization and notification features.

### Tasks for Claude Code

1. Advanced watchlist management:
   - Multiple named watchlists
   - Add/remove coins via command palette
   - Sort by any column
   - Custom columns (pick which metrics to show)

2. Alert system:
   - Price threshold alerts (above/below)
   - Percent change alerts (e.g., BTC drops > 5% in 1h)
   - Fear and Greed threshold alerts
   - Whale movement alerts
   - Terminal bell + highlighted notification bar

3. Portfolio tracker:
   - Manual entry: coin, quantity, buy price
   - PnL calculation (unrealized, realized)
   - Portfolio allocation pie chart (plotext)
   - Cost basis and average buy price

4. Persistent storage:
   - SQLite tables for watchlists, alerts, portfolio entries
   - Import/export to CSV

### Deliverable
Users manage multiple watchlists, set custom alerts, and track a portfolio with PnL from within the terminal.

---

## Stage 7: Polish and Performance

**Goal:** Optimize performance, add keybindings, and finalize UX.

### Tasks for Claude Code

1. Keyboard navigation:
   - Tab switching (F1-F6 for each tab)
   - Arrow keys for list/table navigation
   - `/` for search/filter
   - `q` to quit, `r` to force refresh
   - `?` for help overlay

2. Performance:
   - Async data fetching with httpx
   - Connection pooling
   - Intelligent cache: stale-while-revalidate pattern
   - Background refresh threads per data source
   - Graceful degradation when an API is down

3. Error handling:
   - API rate limit detection and backoff
   - Network failure recovery
   - Invalid API key warnings
   - Timeout handling with retry logic

4. Terminal compatibility:
   - Test with common terminal emulators (iTerm2, Windows Terminal, GNOME Terminal)
   - Responsive layout (adapts to terminal size)
   - Fallback for terminals without Unicode support

5. Documentation:
   - README with installation steps
   - Configuration guide
   - API key setup instructions
   - Screenshots/GIFs of each tab

### Deliverable
A polished, production-grade terminal app with smooth navigation, resilient data fetching, and clear documentation.

---

## Execution Notes for Claude Code

Each stage is self-contained. Complete and test one stage before starting the next. Key principles:

1. Write tests for each data provider (mock API responses).
2. Keep providers loosely coupled. Each implements a base class with `fetch()` and `transform()` methods.
3. Store all API keys in config, never hardcoded.
4. Rate limit all API calls. Log every request for debugging.
5. Use dataclasses or Pydantic models for all data structures.
6. Every panel should handle "no data" states gracefully (show loading or error message, not crash).

### Priority Order if Time-Constrained
Stage 1 > Stage 2 > Stage 3 > Stage 5 > Stage 4 > Stage 6 > Stage 7

Stage 1 and 2 give you a functional price terminal. Stage 3 adds the information edge. Stages 4-7 build depth.
