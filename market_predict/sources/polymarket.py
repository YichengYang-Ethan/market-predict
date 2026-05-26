"""Polymarket Gamma API: read-only access to active markets (no auth required).

Polymarket carries monthly one-touch contracts for S&P 500 (SPX). Each event
("What will S&P 500 (SPX) hit in May 2026?") contains sub-markets like:

    "Will S&P 500 (SPX) hit $7,450 (HIGH) in June?"
    "Will S&P 500 (SPX) hit $6,600 (LOW) in June?"

These resolve YES if the underlying touches the strike at any point during the
period (path-dependent), so probabilities are NOT mutually exclusive — do not
sum them. Display HIGH and LOW as two separate curves.

QQQ/NDX has no equivalent contracts on Polymarket as of 2026-05.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

import requests

BASE = "https://gamma-api.polymarket.com"


@dataclass
class PolyOneTouchBracket:
    """A single 'Will X hit $K (HIGH|LOW) in [period]?' contract."""

    strike: float
    direction: str  # "HIGH" or "LOW"
    yes_price: float  # implied probability of touch
    volume_24h: float
    end_date: str  # ISO date


@dataclass
class PolyEvent:
    title: str
    slug: str
    end_date: str
    volume_24h: float
    brackets: list[PolyOneTouchBracket]


# Underlying-name → list of keywords to match in event titles.
# Polymarket uses "SPY" / "SPX" / "S&P 500" interchangeably; we match any.
UNDERLYING_KEYWORDS: dict[str, tuple[str, ...]] = {
    "S&P 500": ("S&P 500", "SPX", "SPY"),
    "Nasdaq 100": ("Nasdaq 100", "NDX", "QQQ"),  # currently empty on Polymarket
}


_PRICE_PATTERN = re.compile(
    r"\$?([\d,]+(?:\.\d+)?)\s*\(?(HIGH|LOW)\)?", re.IGNORECASE
)


def _parse_one_touch(question: str) -> Optional[tuple[float, str]]:
    """Extract (strike, direction) from a Polymarket question.

    Examples that match:
        "Will S&P 500 (SPX) hit $7,450 (HIGH) in June?"      → (7450, "HIGH")
        "Will Bitcoin hit $150,000 (HIGH) in June?"           → (150000, "HIGH")
    """
    m = _PRICE_PATTERN.search(question)
    if not m:
        return None
    try:
        strike = float(m.group(1).replace(",", ""))
        direction = m.group(2).upper()
        return strike, direction
    except ValueError:
        return None


def _safe_float(s: str | float | int | None) -> float:
    if s is None:
        return 0.0
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def fetch_finance_events(limit: int = 200) -> list[dict]:
    r = requests.get(
        f"{BASE}/events",
        params={"tag_slug": "finance", "active": "true", "closed": "false", "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("data", [])


def fetch_monthly_one_touch(underlying_name: str) -> Optional[PolyEvent]:
    """Find the Polymarket monthly one-touch event for the given underlying.

    Returns the soonest-resolving matching event, or None if none found.
    """
    keywords = UNDERLYING_KEYWORDS.get(underlying_name, ())
    if not keywords:
        return None

    events = fetch_finance_events()
    candidates = []
    for e in events:
        title = e.get("title", "")
        if not any(k.lower() in title.lower() for k in keywords):
            continue
        if "hit" not in title.lower():
            continue
        candidates.append(e)

    if not candidates:
        return None

    # Pick soonest-resolving
    candidates.sort(key=lambda e: e.get("endDate", ""))
    e = candidates[0]

    brackets = []
    for m in e.get("markets", []):
        q = m.get("question", "")
        parsed = _parse_one_touch(q)
        if not parsed:
            continue
        strike, direction = parsed

        # outcomePrices is a JSON-encoded string like '["0.345", "0.655"]'
        prices_raw = m.get("outcomePrices", "[]")
        try:
            import json
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            yes_price = _safe_float(prices[0]) if prices else 0.0
        except (ValueError, IndexError, TypeError):
            yes_price = 0.0

        # Skip "fully resolved" / trivial markets (price = 1 or 0 with no volume)
        vol = _safe_float(m.get("volume24hr", 0))
        if vol == 0 and yes_price in (0.0, 1.0):
            continue

        brackets.append(
            PolyOneTouchBracket(
                strike=strike,
                direction=direction,
                yes_price=yes_price,
                volume_24h=vol,
                end_date=m.get("endDate", "")[:10],
            )
        )

    return PolyEvent(
        title=e.get("title", ""),
        slug=e.get("slug", ""),
        end_date=e.get("endDate", "")[:10],
        volume_24h=_safe_float(e.get("volume24hr", 0)),
        brackets=brackets,
    )
