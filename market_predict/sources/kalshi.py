"""Kalshi public API: read-only access to active markets (no auth required)."""
from __future__ import annotations
import requests

from market_predict.models import KalshiBracket, FedOutcome, FedMeeting
from market_predict.transforms.kalshi_dist import parse_bracket

BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _fetch_markets(series_ticker: str, limit: int = 100) -> list[dict]:
    r = requests.get(
        f"{BASE}/markets",
        params={"series_ticker": series_ticker, "status": "open", "limit": limit},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("markets", [])


def _yes_mid(m: dict) -> float:
    bid = float(m.get("yes_bid_dollars", 0) or 0)
    ask = float(m.get("yes_ask_dollars", 0) or 0)
    return (bid + ask) / 2 if (bid + ask) > 0 else 0


def fetch_brackets(series_ticker: str) -> list[KalshiBracket]:
    out = []
    for m in _fetch_markets(series_ticker):
        kind, lo, hi = parse_bracket(m.get("yes_sub_title", "") or "")
        bid = float(m.get("yes_bid_dollars", 0) or 0)
        ask = float(m.get("yes_ask_dollars", 0) or 0)
        out.append(
            KalshiBracket(
                ticker=m.get("ticker", ""),
                strike_low=lo,
                strike_high=hi,
                kind=kind,
                yes_bid=bid,
                yes_ask=ask,
                yes_mid=(bid + ask) / 2 if (bid + ask) > 0 else 0,
                volume_24h=float(m.get("volume_24h_fp", 0) or 0),
                open_interest=float(m.get("open_interest_fp", 0) or 0),
                close_time=m.get("close_time", "")[:10],
            )
        )
    return [b for b in out if b.yes_mid > 0 and b.kind != "unknown"]


def fetch_fed_meetings(n: int = 3) -> list[FedMeeting]:
    markets = _fetch_markets("KXFEDDECISION")
    by_event: dict[str, list[dict]] = {}
    close_times: dict[str, str] = {}
    for m in markets:
        evt = m.get("event_ticker", "")
        by_event.setdefault(evt, []).append(m)
        close_times[evt] = m.get("close_time", "")[:10]

    meetings = []
    for evt, ms in sorted(by_event.items(), key=lambda kv: close_times.get(kv[0], ""))[:n]:
        outcomes = [
            FedOutcome(
                ticker=m.get("ticker", ""),
                title=m.get("yes_sub_title", "") or m.get("title", "")[:80],
                yes_mid=_yes_mid(m),
                open_interest=float(m.get("open_interest_fp", 0) or 0),
                volume_24h=float(m.get("volume_24h_fp", 0) or 0),
            )
            for m in ms
        ]
        meetings.append(FedMeeting(event_ticker=evt, close_time=close_times[evt], outcomes=outcomes))
    return meetings
