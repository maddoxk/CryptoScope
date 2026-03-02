"""CoinGecko ID to Binance trading pair mapping."""

from __future__ import annotations

# Static map for coins where CoinGecko ID doesn't trivially map to a Binance symbol.
COINGECKO_TO_BINANCE: dict[str, str] = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "binancecoin": "BNBUSDT",
    "solana": "SOLUSDT",
    "ripple": "XRPUSDT",
    "cardano": "ADAUSDT",
    "dogecoin": "DOGEUSDT",
    "polkadot": "DOTUSDT",
    "avalanche-2": "AVAXUSDT",
    "chainlink": "LINKUSDT",
    "polygon-ecosystem-token": "POLUSDT",
    "matic-network": "MATICUSDT",
    "tron": "TRXUSDT",
    "shiba-inu": "SHIBUSDT",
    "litecoin": "LTCUSDT",
    "uniswap": "UNIUSDT",
    "stellar": "XLMUSDT",
    "cosmos": "ATOMUSDT",
    "near": "NEARUSDT",
    "internet-computer": "ICPUSDT",
    "filecoin": "FILUSDT",
    "aptos": "APTUSDT",
    "arbitrum": "ARBUSDT",
    "optimism": "OPUSDT",
    "sui": "SUIUSDT",
    "pepe": "PEPEUSDT",
    "render-token": "RENDERUSDT",
    "injective-protocol": "INJUSDT",
    "the-graph": "GRTUSDT",
    "fetch-ai": "FETUSDT",
}


def coingecko_to_binance(coin_id: str, ticker_symbol: str = "") -> str | None:
    """Convert a CoinGecko coin ID to a Binance trading pair.

    Tries the static map first, then falls back to ``{SYMBOL}USDT``.
    Returns ``None`` when no reasonable mapping can be made.
    """
    if coin_id in COINGECKO_TO_BINANCE:
        return COINGECKO_TO_BINANCE[coin_id]
    if ticker_symbol:
        return f"{ticker_symbol.upper()}USDT"
    return None
