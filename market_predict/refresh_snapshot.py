"""Build TickerView for every ticker in TICKER_MAP and write snapshots.

Invoked by `.github/workflows/refresh-snapshot.yml` every ~15 minutes. The
Action commits any `data/snapshot_*.json` diffs back to the repo, and the
Streamlit app reads those snapshots instead of fetching 18 live APIs each
visit. Exit code is 0 if at least one ticker succeeds, 1 if all failed.
"""
from __future__ import annotations
import sys
from pathlib import Path

from market_predict.cli import build_view
from market_predict.snapshot import save_snapshot
from market_predict.tickers import TICKER_MAP

OUT_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    succeeded = []
    failed = []
    for symbol in TICKER_MAP:
        try:
            print(f"== Building {symbol} ==", file=sys.stderr)
            view = build_view(symbol)
            path = OUT_DIR / f"snapshot_{symbol}.json"
            save_snapshot(view, path)
            size_kb = path.stat().st_size / 1024
            print(f"  wrote {path.name} ({size_kb:.1f} KB)", file=sys.stderr)
            succeeded.append(symbol)
        except Exception as e:
            print(f"  FAILED {symbol}: {type(e).__name__}: {e}", file=sys.stderr)
            failed.append(symbol)

    print(f"\nDone. Succeeded: {succeeded}  Failed: {failed}", file=sys.stderr)
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
