"""Hardcoded ticker → underlying index + Kalshi series mapping.

Adding a new ticker (e.g. IWM) means appending one entry here and confirming
the corresponding Kalshi series has active markets.
"""
from __future__ import annotations

TICKER_MAP: dict[str, dict[str, str]] = {
    "SPY": {
        "underlying_symbol": "^GSPC",
        "underlying_name": "S&P 500",
        "kalshi_yearly": "KXINXY",
        "kalshi_daily": "KXINX",
        "kalshi_year_max": "KXINXMAXY",     # year max one-touch (cumulative above)
        "kalshi_year_min": "KXINXMINY",     # year min one-touch (cumulative below)
        "futures_symbol": "ES=F",
        "futures_name": "ES",
        "spx_to_spy_ratio": 10.0,           # SPX ≈ SPY × 10 (approximate)
    },
    "QQQ": {
        "underlying_symbol": "^NDX",
        "underlying_name": "Nasdaq 100",
        "kalshi_yearly": "KXNASDAQ100Y",
        "kalshi_daily": "KXNASDAQ100",
        "kalshi_year_max": "KXNASDAQ100MAXY",
        "kalshi_year_min": "KXNASDAQ100MINY",
        "futures_symbol": "NQ=F",
        "futures_name": "NQ",
        "spx_to_spy_ratio": 40.0,           # NDX ≈ QQQ × 40 (approximate)
    },
}


def get_config(symbol: str) -> dict[str, str]:
    cfg = TICKER_MAP.get(symbol.upper())
    if not cfg:
        raise ValueError(f"Unknown ticker: {symbol}. Supported: {sorted(TICKER_MAP)}")
    return cfg
