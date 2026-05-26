from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class OptionsWall:
    expiry: date
    call_wall_strike: float
    call_wall_oi: int
    put_wall_strike: float
    put_wall_oi: int
    max_pain: float
    gamma_flip: Optional[float]
    total_call_oi: int
    total_put_oi: int
    atm_iv: float


@dataclass
class KalshiBracket:
    ticker: str
    strike_low: Optional[float]
    strike_high: Optional[float]
    kind: str  # "above" | "below" | "between"
    yes_bid: float
    yes_ask: float
    yes_mid: float
    volume_24h: float
    open_interest: float
    close_time: str


@dataclass
class FedOutcome:
    ticker: str
    title: str
    yes_mid: float
    open_interest: float
    volume_24h: float


@dataclass
class FedMeeting:
    event_ticker: str
    close_time: str
    outcomes: list[FedOutcome]


@dataclass
class KalshiBinary:
    """Single-outcome Kalshi market (binary yes/no, no brackets)."""

    ticker: str
    event_ticker: str
    title: str          # from yes_sub_title or first market title
    yes_mid: float
    yes_bid: float
    yes_ask: float
    open_interest: float
    volume_24h: float
    close_time: str


@dataclass
class TickerView:
    symbol: str
    spot: float
    underlying_name: str
    underlying_value: float
    timestamp: datetime
    options_wall: Optional[OptionsWall]
    kalshi_yearly: list[KalshiBracket]
    fed_meetings: list[FedMeeting]
    # Daily-resolution Kalshi brackets (single-day expiry, lower OI than yearly)
    kalshi_daily: list[KalshiBracket] = field(default_factory=list)
    # Polymarket monthly one-touch (HIGH/LOW); typed Any to keep models.py
    # free of source-specific imports. May be None if no contract available.
    polymarket_monthly: Optional[Any] = None
    polymarket_daily_updown: Optional[Any] = None
    # 3-month OHLCV history (yfinance), VIX snapshot, futures snapshot — all optional.
    history: Optional[Any] = None
    vix: Optional[Any] = None
    futures: Optional[Any] = None
    # Kalshi extra panels (v2)
    kalshi_rate_cut_count: Optional[Any] = None        # FedMeeting reuse (event=KXRATECUTCOUNT)
    kalshi_recession: list[KalshiBinary] = field(default_factory=list)  # KXRECSSNBER (multi-event)
    kalshi_year_max: list[KalshiBracket] = field(default_factory=list)  # one-touch HIGH cumulative
    kalshi_year_min: list[KalshiBracket] = field(default_factory=list)  # one-touch LOW cumulative
    # Polymarket extra panels (v2)
    polymarket_premarket_updown: Optional[Any] = None  # PolyDailyBinary (SPX Opens Up/Down)
    polymarket_daily_close_brackets: Optional[Any] = None  # cumulative "closes above"
    polymarket_fed_decision: Optional[Any] = None      # next FOMC event with outcome markets
    polymarket_rate_cuts_2026: Optional[Any] = None    # "How many Fed rate cuts in 2026"
    polymarket_largest_company: Optional[Any] = None   # ranking event Largest Company end of [period]
    # Optional raw chain (typed Any to avoid hard pandas import in models)
    # Used by the Streamlit UI to draw per-strike OI bars; CLI does not consume.
    calls_chain: Optional[Any] = None
    puts_chain: Optional[Any] = None
    options_expiry: Optional[str] = None
