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
    },
    "QQQ": {
        "underlying_symbol": "^NDX",
        "underlying_name": "Nasdaq 100",
        "kalshi_yearly": "KXNASDAQ100Y",
        "kalshi_daily": "KXNASDAQ100",
    },
}


def get_config(symbol: str) -> dict[str, str]:
    cfg = TICKER_MAP.get(symbol.upper())
    if not cfg:
        raise ValueError(f"Unknown ticker: {symbol}. Supported: {sorted(TICKER_MAP)}")
    return cfg
