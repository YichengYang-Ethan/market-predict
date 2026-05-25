"""Parse Kalshi bracket sub-titles into (kind, strike_low, strike_high) tuples.

Real-world formats observed in the API:
    "9,000.01 or above"       → ("above", 9000.01, None)
    "3,999.99 or below"       → ("below", None, 3999.99)
    "8,800 to 9,000"          → ("between", 8800, 9000)

NOTE: do not infer kind from the ticker suffix (B/T) — it does not map cleanly.
For example "T9000" means "above 9000" but "T4000" means "below 4000". Only
yes_sub_title is reliable.
"""
from __future__ import annotations


def parse_bracket(yes_sub_title: str) -> tuple[str, float | None, float | None]:
    s = yes_sub_title.replace(",", "").strip()
    if "or above" in s:
        try:
            return ("above", float(s.split("or above")[0].strip()), None)
        except ValueError:
            pass
    if "or below" in s:
        try:
            return ("below", None, float(s.split("or below")[0].strip()))
        except ValueError:
            pass
    if " to " in s:
        try:
            lo, hi = s.split(" to ")
            return ("between", float(lo.strip()), float(hi.strip()))
        except ValueError:
            pass
    return ("unknown", None, None)
