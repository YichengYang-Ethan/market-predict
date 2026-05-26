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
    # Optional raw chain (typed Any to avoid hard pandas import in models)
    # Used by the Streamlit UI to draw per-strike OI bars; CLI does not consume.
    calls_chain: Optional[Any] = None
    puts_chain: Optional[Any] = None
    options_expiry: Optional[str] = None
