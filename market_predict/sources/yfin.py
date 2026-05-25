"""yfinance source: spot price + raw options chain for a ticker."""
from __future__ import annotations
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
