"""CLI entry point: python -m market_predict SPY

Fetches 18 independent data sources in parallel via a ThreadPoolExecutor.
Serial fetch is ~100s on cold cache (each yfinance call is 5-15s);
parallel fetch lands around 8-15s, bottlenecked by the slowest single API.
"""
from __future__ import annotations
import sys
from concurrent.futures import ThreadPoolExecutor
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


def _safe(fn, *args, default=None, label=""):
    """Run fn(*args); on any exception, log and return default."""
    try:
        return fn(*args)
    except Exception as exc:
        print(f"  ({label} failed: {exc})", file=sys.stderr)
        return default


def _get_underlying_value(symbol: str) -> float:
    return float(yf.Ticker(symbol).fast_info.last_price)


def build_view(symbol: str) -> TickerView:
    cfg = get_config(symbol)

    print(f"Fetching 18 sources for {symbol} in parallel ...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=18) as pool:
        # yfinance batch
        f_spot = pool.submit(_safe, get_spot, symbol, default=0.0, label="spot")
        f_expirations = pool.submit(_safe, list_expirations, symbol, default=(), label="expirations")
        f_underlying = pool.submit(_safe, _get_underlying_value, cfg["underlying_symbol"], default=0.0, label="underlying")
        f_history = pool.submit(_safe, get_history, symbol, "3mo", default=None, label="history")
        f_vix = pool.submit(get_vix)  # already returns None on failure
        f_futures = pool.submit(get_futures, cfg["futures_symbol"], cfg["futures_name"])

        # Kalshi batch
        f_yearly = pool.submit(_safe, fetch_brackets, cfg["kalshi_yearly"], default=[], label="kalshi yearly")
        f_daily = pool.submit(_safe, fetch_brackets, cfg["kalshi_daily"], default=[], label="kalshi daily")
        f_year_max = pool.submit(_safe, fetch_one_touch_cumulative, cfg["kalshi_year_max"], default=[], label="year max")
        f_year_min = pool.submit(_safe, fetch_one_touch_cumulative, cfg["kalshi_year_min"], default=[], label="year min")
        f_meetings = pool.submit(_safe, fetch_fed_meetings, default=[], label="fed meetings")
        f_rate_count = pool.submit(_safe, fetch_event_outcomes, "KXRATECUTCOUNT", default=None, label="rate cut count")
        f_recession = pool.submit(_safe, fetch_binary_events, "KXRECSSNBER", default=[], label="recession")

        # Polymarket batch
        f_poly_monthly = pool.submit(_safe, fetch_monthly_one_touch, cfg["underlying_name"], default=None, label="poly monthly")
        f_poly_daily = pool.submit(_safe, fetch_daily_up_down, cfg["underlying_name"], default=None, label="poly daily")
        f_poly_premarket = pool.submit(_safe, fetch_premarket_updown, cfg["underlying_name"], default=None, label="poly premarket")
        f_poly_close = pool.submit(_safe, fetch_daily_close_brackets, cfg["underlying_name"], default=None, label="poly close")
        f_poly_fed = pool.submit(_safe, fetch_fed_decision_event, default=None, label="poly fed")
        f_poly_cuts = pool.submit(_safe, fetch_rate_cuts_count_2026, default=None, label="poly cuts")
        f_poly_largest = pool.submit(_safe, fetch_largest_company_event, default=None, label="poly largest")

        # Resolve with a hard 15s per-future deadline. yfinance has internal
        # retry loops that can hang 60+ seconds on rate-limited shared IPs;
        # we'd rather show "n/a" than make the user wait 2 minutes.
        from concurrent.futures import TimeoutError as FuturesTimeout

        def _r(fut, default, label):
            try:
                return fut.result(timeout=15)
            except FuturesTimeout:
                print(f"  ({label} timed out after 15s)", file=sys.stderr)
                return default
            except Exception as exc:
                print(f"  ({label} raised: {exc})", file=sys.stderr)
                return default

        spot = _r(f_spot, 0.0, "spot")
        expirations = _r(f_expirations, (), "expirations")
        underlying_value = _r(f_underlying, 0.0, "underlying")
        history = _r(f_history, None, "history")
        vix = _r(f_vix, None, "vix")
        futures = _r(f_futures, None, "futures")
        yearly = _r(f_yearly, [], "yearly")
        daily = _r(f_daily, [], "daily")
        year_max = _r(f_year_max, [], "year_max")
        year_min = _r(f_year_min, [], "year_min")
        meetings = _r(f_meetings, [], "meetings")
        rate_cut_count = _r(f_rate_count, None, "rate_cut_count")
        recession = _r(f_recession, [], "recession")
        poly_monthly = _r(f_poly_monthly, None, "poly_monthly")
        poly_daily = _r(f_poly_daily, None, "poly_daily")
        poly_premarket = _r(f_poly_premarket, None, "poly_premarket")
        poly_close_brackets = _r(f_poly_close, None, "poly_close")
        poly_fed = _r(f_poly_fed, None, "poly_fed")
        poly_cuts = _r(f_poly_cuts, None, "poly_cuts")
        poly_largest = _r(f_poly_largest, None, "poly_largest")

    # Options chain depends on spot + expirations → fetch sequentially after
    expiry = pick_near_monthly_expiry(expirations) if expirations else None
    wall = None
    calls = puts = None
    if expiry and spot:
        try:
            calls, puts = get_options_chain(symbol, expiry)
            wall = compute_wall(spot, expiry, calls, puts)
        except Exception as exc:
            print(f"  (options chain failed: {exc})", file=sys.stderr)

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
