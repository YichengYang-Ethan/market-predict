"""CLI entry point: python -m market_predict SPY"""
from __future__ import annotations
import sys
from datetime import datetime

import yfinance as yf

from market_predict.models import TickerView
from market_predict.render import render
from market_predict.sources.kalshi import fetch_brackets, fetch_fed_meetings
from market_predict.sources.polymarket import fetch_monthly_one_touch
from market_predict.sources.yfin import (
    get_options_chain,
    get_spot,
    list_expirations,
    pick_near_monthly_expiry,
)
from market_predict.tickers import TICKER_MAP, get_config
from market_predict.transforms.walls import compute_wall


def build_view(symbol: str) -> TickerView:
    cfg = get_config(symbol)

    print(f"Fetching {symbol} spot + chain ...", file=sys.stderr)
    spot = get_spot(symbol)
    expirations = list_expirations(symbol)
    expiry = pick_near_monthly_expiry(expirations)
    wall = None
    calls = puts = None
    if expiry:
        calls, puts = get_options_chain(symbol, expiry)
        wall = compute_wall(spot, expiry, calls, puts)

    print(f"Fetching underlying {cfg['underlying_symbol']} ...", file=sys.stderr)
    underlying_value = float(yf.Ticker(cfg["underlying_symbol"]).fast_info.last_price)

    print(f"Fetching Kalshi {cfg['kalshi_yearly']} (yearly) ...", file=sys.stderr)
    yearly = fetch_brackets(cfg["kalshi_yearly"])

    print(f"Fetching Kalshi {cfg['kalshi_daily']} (daily) ...", file=sys.stderr)
    daily = fetch_brackets(cfg["kalshi_daily"])

    print(f"Fetching Polymarket monthly one-touch ...", file=sys.stderr)
    try:
        poly_monthly = fetch_monthly_one_touch(cfg["underlying_name"])
    except Exception as exc:
        print(f"  (Polymarket fetch failed: {exc})", file=sys.stderr)
        poly_monthly = None

    print(f"Fetching Fed path ...", file=sys.stderr)
    meetings = fetch_fed_meetings()

    return TickerView(
        symbol=symbol.upper(),
        spot=spot,
        underlying_name=cfg["underlying_name"],
        underlying_value=underlying_value,
        timestamp=datetime.now(),
        options_wall=wall,
        kalshi_yearly=yearly,
        kalshi_daily=daily,
        polymarket_monthly=poly_monthly,
        fed_meetings=meetings,
        calls_chain=calls,
        puts_chain=puts,
        options_expiry=expiry,
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: python -m market_predict {{{ '|'.join(TICKER_MAP) }}}", file=sys.stderr)
        return 1
    view = build_view(sys.argv[1])
    render(view)
    return 0


if __name__ == "__main__":
    sys.exit(main())
