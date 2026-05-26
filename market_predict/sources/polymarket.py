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


@dataclass
class PolyDailyBinary:
    """Single 'Up or Down today' bet — P(close > open today)."""

    title: str
    end_date: str
    p_up: float
    p_down: float
    volume_24h: float


@dataclass
class PolyCloseBracket:
    """Polymarket 'closes above $X' market — cumulative probability."""

    strike: float       # SPY price (or whatever ETF)
    yes_price: float    # P(close >= strike)
    volume_24h: float


@dataclass
class PolyCloseBracketsEvent:
    title: str
    end_date: str
    volume_24h: float
    brackets: list[PolyCloseBracket]


@dataclass
class PolyOutcomeMarket:
    """One outcome within an event like 'Fed Decision in June' or 'Rate Cuts Count'."""

    question: str
    yes_price: float
    volume_24h: float
    open_interest: float


@dataclass
class PolyOutcomeEvent:
    title: str
    slug: str
    end_date: str
    volume_24h: float
    markets: list[PolyOutcomeMarket]


@dataclass
class PolyRankingRow:
    """One company in a 'Largest Company' style ranking event."""

    name: str          # groupItemTitle
    yes_price: float
    volume_24h: float


@dataclass
class PolyRankingEvent:
    title: str
    end_date: str
    volume_24h: float
    rows: list[PolyRankingRow]


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


def fetch_daily_close_events(limit: int = 200) -> list[dict]:
    """Polymarket's daily up/down + 'closes above X' events all share tag_slug=daily-close."""
    r = requests.get(
        f"{BASE}/events",
        params={"tag_slug": "daily-close", "active": "true", "closed": "false", "limit": limit},
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


def fetch_daily_up_down(underlying_name: str) -> Optional[PolyDailyBinary]:
    """Find the most recent (closest-to-today) Polymarket daily up/down event.

    Polymarket creates one event per ticker per trading day with title format:
        "<NAME> (TICKER) Up or Down on <Month> <Day>?"
    Each event has exactly one binary market with outcomes ["Up", "Down"].

    For S&P 500 we prefer the ETF version (SPY) over the SPX cash-index version
    because the ETF matches the spot price the dashboard quotes; they price
    slightly differently (dividend drift, 9:30 open vs settlement).
    """
    keywords = UNDERLYING_KEYWORDS.get(underlying_name, ())
    if not keywords:
        return None

    today = __import__("datetime").date.today().isoformat()
    events = fetch_daily_close_events()
    candidates = []
    for e in events:
        title = e.get("title", "")
        if "up or down" not in title.lower():
            continue
        if not any(k.lower() in title.lower() for k in keywords):
            continue
        end = e.get("endDate", "")[:10]
        if end < today:
            continue  # skip already-resolved
        candidates.append(e)

    if not candidates:
        return None

    etf_keywords = {"S&P 500": "spy", "Nasdaq 100": "qqq"}
    etf_kw = etf_keywords.get(underlying_name, "").lower()

    def sort_key(e):
        title_lower = e.get("title", "").lower()
        prefers_etf = 0 if etf_kw and f"({etf_kw})" in title_lower else 1
        return (e.get("endDate", ""), prefers_etf)

    candidates.sort(key=sort_key)
    e = candidates[0]
    markets = e.get("markets") or []
    if not markets:
        return None
    m = markets[0]

    import json
    prices_raw = m.get("outcomePrices", "[]")
    try:
        prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
    except (ValueError, TypeError):
        prices = []
    if len(prices) < 2:
        return None

    p_up = _safe_float(prices[0])
    p_down = _safe_float(prices[1])

    return PolyDailyBinary(
        title=e.get("title", ""),
        end_date=e.get("endDate", "")[:10],
        p_up=p_up,
        p_down=p_down,
        volume_24h=_safe_float(e.get("volume24hr", 0)),
    )


def fetch_premarket_updown(underlying_name: str) -> Optional[PolyDailyBinary]:
    """Polymarket 'X Opens Up or Down' — pre-market direction binary."""
    keywords = UNDERLYING_KEYWORDS.get(underlying_name, ())
    if not keywords:
        return None

    today = __import__("datetime").date.today().isoformat()
    events = fetch_daily_close_events()
    candidates = []
    for e in events:
        title = e.get("title", "")
        if "opens up or down" not in title.lower():
            continue
        if not any(k.lower() in title.lower() for k in keywords):
            continue
        end = e.get("endDate", "")[:10]
        if end < today:
            continue
        candidates.append(e)
    if not candidates:
        return None
    candidates.sort(key=lambda e: e.get("endDate", ""))
    e = candidates[0]
    markets = e.get("markets") or []
    if not markets:
        return None
    m = markets[0]
    import json
    try:
        prices = json.loads(m.get("outcomePrices", "[]"))
    except (ValueError, TypeError):
        prices = []
    if len(prices) < 2:
        return None
    return PolyDailyBinary(
        title=e.get("title", ""),
        end_date=e.get("endDate", "")[:10],
        p_up=_safe_float(prices[0]),
        p_down=_safe_float(prices[1]),
        volume_24h=_safe_float(e.get("volume24hr", 0)),
    )


_CLOSE_ABOVE_PATTERN = re.compile(r"\$([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def fetch_daily_close_brackets(underlying_name: str) -> Optional[PolyCloseBracketsEvent]:
    """Polymarket 'X closes above ___ on [today]' — cumulative bracket distribution."""
    keywords = UNDERLYING_KEYWORDS.get(underlying_name, ())
    if not keywords:
        return None
    today = __import__("datetime").date.today().isoformat()
    events = fetch_daily_close_events()
    candidates = []
    for e in events:
        title = e.get("title", "")
        if "closes above" not in title.lower():
            continue
        if not any(k.lower() in title.lower() for k in keywords):
            continue
        end = e.get("endDate", "")[:10]
        if end < today:
            continue
        candidates.append(e)
    if not candidates:
        return None
    candidates.sort(key=lambda e: e.get("endDate", ""))
    e = candidates[0]
    import json
    brackets = []
    for m in e.get("markets", []):
        q = m.get("question", "")
        match = _CLOSE_ABOVE_PATTERN.search(q)
        if not match:
            continue
        try:
            strike = float(match.group(1).replace(",", ""))
        except ValueError:
            continue
        try:
            prices = json.loads(m.get("outcomePrices", "[]"))
            yes_price = _safe_float(prices[0]) if prices else 0
        except (ValueError, TypeError, IndexError):
            yes_price = 0
        if yes_price <= 0 or yes_price >= 1:
            # Skip trivially resolved
            continue
        brackets.append(PolyCloseBracket(
            strike=strike,
            yes_price=yes_price,
            volume_24h=_safe_float(m.get("volume24hr", 0)),
        ))
    brackets.sort(key=lambda b: b.strike)
    return PolyCloseBracketsEvent(
        title=e.get("title", ""),
        end_date=e.get("endDate", "")[:10],
        volume_24h=_safe_float(e.get("volume24hr", 0)),
        brackets=brackets,
    )


def _fetch_event_by_title_substring(
    tag_slugs: tuple[str, ...], title_substring: str
) -> Optional[dict]:
    """Find soonest-resolving event whose title contains substring across given tags.

    Tags are fetched in parallel — Polymarket lists `fed-rates` / `fed` /
    `jerome-powell` separately, and a 3x serial GET adds ~10s on a slow link.
    """
    from concurrent.futures import ThreadPoolExecutor
    today = __import__("datetime").date.today().isoformat()

    def fetch_tag(tag: str) -> list[dict]:
        try:
            r = requests.get(
                f"{BASE}/events",
                params={"tag_slug": tag, "active": "true", "closed": "false", "limit": 200},
                timeout=15,
            )
            data = r.json()
            return data if isinstance(data, list) else data.get("data", [])
        except Exception:
            return []

    all_events: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(tag_slugs)) as ex:
        for evs in ex.map(fetch_tag, tag_slugs):
            for e in evs:
                all_events[e.get("id")] = e
    candidates = [
        e for e in all_events.values()
        if title_substring.lower() in e.get("title", "").lower()
        and e.get("endDate", "")[:10] >= today
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda e: e.get("endDate", ""))
    return candidates[0]


def _make_outcome_event(e: dict) -> PolyOutcomeEvent:
    import json
    outcomes = []
    for m in e.get("markets", []):
        try:
            prices = json.loads(m.get("outcomePrices", "[]"))
            yes = _safe_float(prices[0]) if prices else 0
        except (ValueError, TypeError, IndexError):
            yes = 0
        outcomes.append(PolyOutcomeMarket(
            question=m.get("question", ""),
            yes_price=yes,
            volume_24h=_safe_float(m.get("volume24hr", 0)),
            open_interest=_safe_float(m.get("liquidity", 0)),
        ))
    return PolyOutcomeEvent(
        title=e.get("title", ""),
        slug=e.get("slug", ""),
        end_date=e.get("endDate", "")[:10],
        volume_24h=_safe_float(e.get("volume24hr", 0)),
        markets=outcomes,
    )


def fetch_fed_decision_event() -> Optional[PolyOutcomeEvent]:
    """Soonest 'Fed Decision in [month]' event with binary outcome markets."""
    e = _fetch_event_by_title_substring(
        ("fed", "fed-rates", "jerome-powell"), "Fed Decision in"
    )
    return _make_outcome_event(e) if e else None


def fetch_rate_cuts_count_2026() -> Optional[PolyOutcomeEvent]:
    """'How many Fed rate cuts in 2026?' event."""
    e = _fetch_event_by_title_substring(
        ("fed", "fed-rates"), "How many Fed rate cuts"
    )
    return _make_outcome_event(e) if e else None


def fetch_largest_company_event() -> Optional[PolyRankingEvent]:
    """Soonest 'Largest Company end of [period]' ranking event."""
    e = _fetch_event_by_title_substring(
        ("big-tech", "tech", "business"), "Largest Company end of"
    )
    if e is None:
        return None
    import json
    rows = []
    for m in e.get("markets", []):
        name = m.get("groupItemTitle", "") or m.get("question", "")[:40]
        # Skip placeholder rows: "Company A".."Company T" template slots and
        # the catch-all "Other" outcome — neither has volume or signal.
        if name.lower().startswith("company ") or name.strip().lower() == "other":
            continue
        try:
            prices = json.loads(m.get("outcomePrices", "[]"))
            yes = _safe_float(prices[0]) if prices else 0
        except (ValueError, TypeError, IndexError):
            yes = 0
        rows.append(PolyRankingRow(
            name=name,
            yes_price=yes,
            volume_24h=_safe_float(m.get("volume24hr", 0)),
        ))
    rows.sort(key=lambda r: -r.yes_price)
    return PolyRankingEvent(
        title=e.get("title", ""),
        end_date=e.get("endDate", "")[:10],
        volume_24h=_safe_float(e.get("volume24hr", 0)),
        rows=rows,
    )
