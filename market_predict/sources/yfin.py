"""yfinance source: spot price + raw options chain + history/VIX/futures."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf


def get_spot(symbol: str) -> float:
    return float(yf.Ticker(symbol).fast_info.last_price)


def pick_near_monthly_expiry(expirations: tuple[str, ...], min_days: int = 21) -> Optional[str]:
    today = date.today()
    for exp_str in expirations:
        if (datetime.strptime(exp_str, "%Y-%m-%d").date() - today).days >= min_days:
            return exp_str
    return expirations[-1] if expirations else None


def get_options_chain(symbol: str, expiry: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    t = yf.Ticker(symbol)
    chain = t.option_chain(expiry)
    return chain.calls.copy(), chain.puts.copy()


def list_expirations(symbol: str) -> tuple[str, ...]:
    return yf.Ticker(symbol).options


# ─────────────────── new: history, VIX, futures ───────────────────


def get_history(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """OHLCV bars. yfinance returns index=Date, columns=Open/High/Low/Close/Volume."""
    df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@dataclass
class VIXSnapshot:
    current: float
    history_30d: pd.DataFrame  # index=date, columns=Close
    mean_30d: float


def get_vix() -> Optional[VIXSnapshot]:
    try:
        t = yf.Ticker("^VIX")
        current = float(t.fast_info.last_price)
        hist = t.history(period="1mo", auto_adjust=False)
        if hist.empty:
            return None
        hist.index = pd.to_datetime(hist.index).tz_localize(None)
        return VIXSnapshot(
            current=current,
            history_30d=hist[["Close"]],
            mean_30d=float(hist["Close"].mean()),
        )
    except Exception:
        return None


@dataclass
class FuturesSnapshot:
    symbol: str           # "ES=F"
    name: str             # "ES"
    last: float
    previous_close: float
    change_pct: float     # vs previous close (overnight delta)


def get_futures(symbol: str, name: str) -> Optional[FuturesSnapshot]:
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        last = float(info.last_price)
        prev = float(info.previous_close) if info.previous_close else last
        change_pct = (last - prev) / prev * 100 if prev else 0.0
        return FuturesSnapshot(
            symbol=symbol,
            name=name,
            last=last,
            previous_close=prev,
            change_pct=change_pct,
        )
    except Exception:
        return None
