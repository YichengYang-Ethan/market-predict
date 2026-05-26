"""CLI entry point: python -m market_predict SPY"""
from __future__ import annotations
import sys
from datetime import datetime

import yfinance as yf

from market_predict.models import TickerView
from market_predict.render import render
from market_predict.sources.kalshi import (
    fetch_binary_events,
    fetch_brackets,
    fetch_event_outcomes,
    fetch_fed_meetings,
    fetch_one_touch_cumulative,
)
from market_predict.sources.polymarket import (
    fetch_daily_close_brackets,
    fetch_daily_up_down,
    fetch_fed_decision_event,
    fetch_largest_company_event,
    fetch_monthly_one_touch,
    fetch_premarket_updown,
    fetch_rate_cuts_count_2026,
)
from market_predict.sources.yfin import (
    get_futures,
    get_history,
    get_options_chain,
    get_spot,
    get_vix,
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

    print(f"Fetching {symbol} 3mo history ...", file=sys.stderr)
    history = get_history(symbol, period="3mo")

    print(f"Fetching VIX ...", file=sys.stderr)
    vix = get_vix()

    print(f"Fetching futures {cfg['futures_symbol']} ...", file=sys.stderr)
    futures = get_futures(cfg["futures_symbol"], cfg["futures_name"])

    print(f"Fetching Kalshi {cfg['kalshi_yearly']} (yearly) ...", file=sys.stderr)
    yearly = fetch_brackets(cfg["kalshi_yearly"])

    print(f"Fetching Kalshi {cfg['kalshi_daily']} (daily) ...", file=sys.stderr)
    daily = fetch_brackets(cfg["kalshi_daily"])

    print(f"Fetching Polymarket monthly one-touch ...", file=sys.stderr)
    try:
        poly_monthly = fetch_monthly_one_touch(cfg["underlying_name"])
    except Exception as exc:
        print(f"  (Polymarket monthly fetch failed: {exc})", file=sys.stderr)
        poly_monthly = None

    print(f"Fetching Polymarket daily up/down ...", file=sys.stderr)
    try:
        poly_daily = fetch_daily_up_down(cfg["underlying_name"])
    except Exception as exc:
        print(f"  (Polymarket daily fetch failed: {exc})", file=sys.stderr)
        poly_daily = None

    print(f"Fetching Fed path ...", file=sys.stderr)
    meetings = fetch_fed_meetings()

    # ─── v2 additions ───
    print(f"Fetching Kalshi rate-cut count + recession + year MAX/MIN ...", file=sys.stderr)
    try:
        rate_cut_count = fetch_event_outcomes("KXRATECUTCOUNT")
    except Exception as e:
        print(f"  (rate cut count: {e})", file=sys.stderr); rate_cut_count = None
    try:
        recession = fetch_binary_events("KXRECSSNBER")
    except Exception as e:
        print(f"  (recession: {e})", file=sys.stderr); recession = []
    try:
        year_max = fetch_one_touch_cumulative(cfg["kalshi_year_max"])
    except Exception as e:
        print(f"  (year max: {e})", file=sys.stderr); year_max = []
    try:
        year_min = fetch_one_touch_cumulative(cfg["kalshi_year_min"])
    except Exception as e:
        print(f"  (year min: {e})", file=sys.stderr); year_min = []

    print(f"Fetching Polymarket premarket + close brackets + Fed/rate cuts + ranking ...", file=sys.stderr)
    try:
        poly_premarket = fetch_premarket_updown(cfg["underlying_name"])
    except Exception as e:
        print(f"  (premarket: {e})", file=sys.stderr); poly_premarket = None
    try:
        poly_close_brackets = fetch_daily_close_brackets(cfg["underlying_name"])
    except Exception as e:
        print(f"  (close brackets: {e})", file=sys.stderr); poly_close_brackets = None
    try:
        poly_fed = fetch_fed_decision_event()
    except Exception as e:
        print(f"  (poly fed: {e})", file=sys.stderr); poly_fed = None
    try:
        poly_cuts = fetch_rate_cuts_count_2026()
    except Exception as e:
        print(f"  (poly cuts: {e})", file=sys.stderr); poly_cuts = None
    try:
        poly_largest = fetch_largest_company_event()
    except Exception as e:
        print(f"  (largest: {e})", file=sys.stderr); poly_largest = None

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
        polymarket_daily_updown=poly_daily,
        fed_meetings=meetings,
        calls_chain=calls,
        puts_chain=puts,
        options_expiry=expiry,
        history=history,
        vix=vix,
        futures=futures,
        kalshi_rate_cut_count=rate_cut_count,
        kalshi_recession=recession,
        kalshi_year_max=year_max,
        kalshi_year_min=year_min,
        polymarket_premarket_updown=poly_premarket,
        polymarket_daily_close_brackets=poly_close_brackets,
        polymarket_fed_decision=poly_fed,
        polymarket_rate_cuts_2026=poly_cuts,
        polymarket_largest_company=poly_largest,
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
