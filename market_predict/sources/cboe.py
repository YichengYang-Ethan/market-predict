"""CBOE delayed-quotes options source (free, no auth) — drop-in for yfin chain.

Why this over yfinance: yfinance returns empty / zero open interest for the big
ETF chains (SPY/QQQ) outside regular trading hours, so the wall panel goes dark
every evening and weekend. CBOE's delayed-quote CDN returns the *last session's*
snapshot 24/7 — and open interest is an end-of-day figure anyway (OCC publishes
it pre-open), so a delayed snapshot is exactly the right granularity for walls /
max pain. It also ships exchange-computed greeks (delta, gamma, theta, vega) so
we no longer have to solve IV/gamma ourselves.

Endpoint (undocumented CDN behind cboe.com's delayed-quote pages):
    https://cdn.cboe.com/api/global/delayed_quotes/options/{SYM}.json
Indices are prefixed with an underscore (_SPX, _VIX, _NDX); ETFs/stocks are not.
Each contract carries open_interest, iv, delta, gamma, theta, vega, bid, ask,
volume; the top level carries current_price / close.

Public interface mirrors yfin so cli.py only swaps the import:
    list_expirations(symbol)        -> tuple[str, ...]   (YYYY-MM-DD, sorted)
    get_options_chain(symbol, exp)  -> (calls_df, puts_df)
Returned frames use yfinance-compatible column names (strike, openInterest,
impliedVolatility) plus extras (volume, delta, gamma) for future use.
"""
from __future__ import annotations
import threading
import time
from typing import Optional

import pandas as pd
import requests

BASE = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"

# CBOE prefixes cash indices with an underscore; ETFs/stocks are bare. The
# dashboard fetches the ETF chain (walls are computed on the ETF spot), so the
# map is mostly passthrough — listed here so adding index walls later is a
# one-line change.
_CBOE_SYMBOL: dict[str, str] = {
    "SPX": "_SPX",
    "NDX": "_NDX",
    "VIX": "_VIX",
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (market-predict; +https://github.com/YichengYang-Ethan/market-predict)"}

# One network round-trip per symbol is ~8-13s and the full payload is identical
# for both list_expirations and get_options_chain within a single build_view, so
# cache the parsed frame briefly to collapse them into one fetch.
_CACHE_TTL = 180.0
_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def _cboe_symbol(symbol: str) -> str:
    return _CBOE_SYMBOL.get(symbol.upper(), symbol.upper())


def _parse_osi(option_symbol: str) -> Optional[tuple[str, str, float]]:
    """OSI symbol -> (expiry YYYY-MM-DD, 'C'|'P', strike).

    Layout is a fixed 15-char tail (YYMMDD + C/P + strike*1000 zero-padded to 8)
    after a variable-length root, e.g. 'SPY260529C00435000' or
    'SPX260618C00200000'. Slicing from the right is robust to root length.
    """
    body = option_symbol[-15:]
    if len(body) < 15 or body[6] not in ("C", "P"):
        return None
    try:
        expiry = f"20{body[0:2]}-{body[2:4]}-{body[4:6]}"
        cp = body[6]
        strike = int(body[7:15]) / 1000.0
    except ValueError:
        return None
    return expiry, cp, strike


def _fetch_raw(cboe_sym: str) -> dict:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = requests.get(BASE.format(sym=cboe_sym), headers=_HEADERS, timeout=25)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(1.0)
    raise last_exc  # type: ignore[misc]


def _build_df(payload: dict) -> pd.DataFrame:
    options = payload.get("data", {}).get("options", []) or []
    rows = []
    for o in options:
        parsed = _parse_osi(o.get("option", ""))
        if parsed is None:
            continue
        expiry, cp, strike = parsed
        rows.append(
            {
                "expiry": expiry,
                "type": cp,
                "strike": strike,
                "openInterest": float(o.get("open_interest") or 0),
                "impliedVolatility": float(o.get("iv") or 0),
                "volume": float(o.get("volume") or 0),
                "delta": float(o.get("delta") or 0),
                "gamma": float(o.get("gamma") or 0),
            }
        )
    return pd.DataFrame(rows)


def _get_df(symbol: str) -> pd.DataFrame:
    cboe_sym = _cboe_symbol(symbol)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cboe_sym)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    df = _build_df(_fetch_raw(cboe_sym))
    with _lock:
        _cache[cboe_sym] = (time.monotonic(), df)
    return df


def list_expirations(symbol: str) -> tuple[str, ...]:
    df = _get_df(symbol)
    if df.empty:
        return ()
    return tuple(sorted(df["expiry"].unique()))


def get_options_chain(symbol: str, expiry: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _get_df(symbol)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()
    sub = df[df["expiry"] == expiry]
    cols = ["strike", "openInterest", "impliedVolatility", "volume", "delta", "gamma"]
    calls = sub[sub["type"] == "C"][cols].reset_index(drop=True)
    puts = sub[sub["type"] == "P"][cols].reset_index(drop=True)
    return calls, puts
