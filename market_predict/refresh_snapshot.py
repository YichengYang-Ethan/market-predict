"""Build TickerView for every ticker in TICKER_MAP and write snapshots.

Invoked by `.github/workflows/refresh-snapshot.yml` every ~15 minutes. The
Action commits any `data/snapshot_*.json` diffs back to the repo, and the
Streamlit app reads those snapshots instead of fetching 18 live APIs each
visit. Exit code is 0 if at least one ticker succeeds, 1 if all failed.

Fallback merge: Kalshi rate-limits the GitHub Actions IP regularly (429),
so any single run typically loses 1-3 fields. Before writing, we pull the
previous snapshot from the snapshots branch and back-fill missing fields
from it. This keeps the dashboard populated across transient failures —
slightly stale data beats blank panels.
"""
from __future__ import annotations
import sys
from pathlib import Path

import requests

from market_predict.cli import build_view
from market_predict.snapshot import load_snapshot_from_text, save_snapshot
from market_predict.tickers import TICKER_MAP

OUT_DIR = Path(__file__).resolve().parent.parent / "data"
PREVIOUS_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/YichengYang-Ethan/market-predict/"
    "snapshots/data/snapshot_{symbol}.json"
)

# Fields that are safe to back-fill from the previous snapshot when the current
# build returned None / empty list (typically Kalshi 429 or Polymarket timeout).
# Excluded:
#   - options_wall: None is a real state (Yahoo no longer publishes near-spot OI
#     for SPY/QQQ), not a transient failure. Reintroducing an old wall would
#     misrepresent.
#   - calls_chain / puts_chain: large pandas DataFrames; fallback adds bytes
#     with no chart consumer (charts.options_wall only uses options_wall).
#   - spot / underlying_value / history / vix / futures: yfinance failures are
#     rare and we'd rather show "n/a" than a stale price.
FALLBACK_FIELDS = (
    "kalshi_yearly",
    "kalshi_daily",
    "kalshi_year_max",
    "kalshi_year_min",
    "kalshi_rate_cut_count",
    "kalshi_recession",
    "fed_meetings",
    "polymarket_monthly",
    "polymarket_daily_updown",
    "polymarket_premarket_updown",
    "polymarket_daily_close_brackets",
    "polymarket_fed_decision",
    "polymarket_rate_cuts_2026",
    "polymarket_largest_company",
)


def _is_missing(v) -> bool:
    return v is None or (isinstance(v, list) and len(v) == 0)


def _load_previous(symbol: str):
    try:
        r = requests.get(PREVIOUS_SNAPSHOT_URL.format(symbol=symbol), timeout=10)
        if r.ok:
            return load_snapshot_from_text(r.text)
    except requests.RequestException:
        pass
    return None


def _merge_fallback(new_view, old_view) -> int:
    """For each FALLBACK_FIELDS on new_view that's None or [], copy from old_view.
    Returns the number of fields restored from the previous snapshot."""
    if old_view is None:
        return 0
    restored = 0
    for f in FALLBACK_FIELDS:
        if _is_missing(getattr(new_view, f, None)):
            old_v = getattr(old_view, f, None)
            if not _is_missing(old_v):
                setattr(new_view, f, old_v)
                print(f"  fallback: {f} ← previous snapshot", file=sys.stderr)
                restored += 1
    return restored


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    succeeded = []
    failed = []
    for symbol in TICKER_MAP:
        try:
            print(f"== Building {symbol} ==", file=sys.stderr)
            view = build_view(symbol)
            previous = _load_previous(symbol)
            restored = _merge_fallback(view, previous)
            path = OUT_DIR / f"snapshot_{symbol}.json"
            save_snapshot(view, path)
            size_kb = path.stat().st_size / 1024
            tag = f" (+{restored} from previous)" if restored else ""
            print(f"  wrote {path.name} ({size_kb:.1f} KB){tag}", file=sys.stderr)
            succeeded.append(symbol)
        except Exception as e:
            print(f"  FAILED {symbol}: {type(e).__name__}: {e}", file=sys.stderr)
            failed.append(symbol)

    print(f"\nDone. Succeeded: {succeeded}  Failed: {failed}", file=sys.stderr)
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
