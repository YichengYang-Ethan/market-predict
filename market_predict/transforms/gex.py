"""Dealer gamma-exposure (GEX) profile.

Net dealer gamma as a function of underlying price, on the same convention as
transforms.walls (dealers long calls / short puts). The zero crossing is the
gamma-flip level that walls.compute_wall already finds; this exposes the whole
curve so it can be drawn. Computed from the raw chain already carried in the
snapshot (view.calls_chain / view.puts_chain) — no new fetch.

Magnitude is indicative ($bn of dealer gamma per 1% move) and depends on how
complete the CBOE OI is; the *shape* and the zero crossing are the signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from market_predict.transforms.walls import _bsm_gamma


@dataclass
class GexProfile:
    spots: list[float]
    net_gex: list[float]          # $bn of dealer gamma per 1% move, by spot
    zero_gamma: Optional[float]   # interpolated zero crossing (= gamma flip)
    spot: float
    total_gex: float              # net GEX at current spot ($bn/1%)


def _expiry_T(expiry_str: str) -> float:
    exp = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return max((exp - date.today()).days, 1) / 365


def _near_oi(df: pd.DataFrame, spot: float) -> pd.DataFrame:
    d = df[(df.strike >= spot * 0.75) & (df.strike <= spot * 1.25)]
    return d[d.openInterest > 0]


def gex_profile(
    spot: float,
    expiry_str: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    atm_iv: float,
    r: float = 0.04,
    n: int = 41,
    span: float = 0.08,
) -> Optional[GexProfile]:
    if not spot or spot <= 0 or calls is None or puts is None:
        return None
    sigma = atm_iv if atm_iv and atm_iv > 0 else 0.20
    T = _expiry_T(expiry_str)
    c, p = _near_oi(calls, spot), _near_oi(puts, spot)
    if len(c) == 0 and len(p) == 0:
        return None

    spots = np.linspace(spot * (1 - span), spot * (1 + span), n)
    net = []
    for s in spots:
        call_g = sum(
            row.openInterest * _bsm_gamma(s, row.strike, T, r, sigma) * 100 * s * s * 0.01
            for _, row in c.iterrows()
        )
        put_g = sum(
            -row.openInterest * _bsm_gamma(s, row.strike, T, r, sigma) * 100 * s * s * 0.01
            for _, row in p.iterrows()
        )
        net.append(float(call_g + put_g))

    zero = None
    for i in range(len(net) - 1):
        if net[i] * net[i + 1] < 0:
            s0, g0 = spots[i], net[i]
            s1, g1 = spots[i + 1], net[i + 1]
            zero = float(s0 - g0 * (s1 - s0) / (g1 - g0))
            break

    net_bn = [x / 1e9 for x in net]
    total = float(np.interp(spot, spots, net)) / 1e9
    return GexProfile(
        spots=[float(x) for x in spots],
        net_gex=net_bn,
        zero_gamma=zero,
        spot=float(spot),
        total_gex=total,
    )
