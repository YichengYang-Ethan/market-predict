"""Options wall metrics: call/put wall, max pain, gamma flip, ATM IV.

Wall logic: report near-the-money OI peaks (±8%) rather than absolute max OI,
since absolute max often sits at deep-OTM crash hedges that are not tradable
inflection points.

Gamma flip uses BSM gamma summed across all OI at each test spot. Dealers
assumed long calls / short puts (street convention) → net dealer gamma is
sum(call OI × γ) − sum(put OI × γ). Zero crossing is found by linear
interpolation across a 41-point spot grid spanning ±10%.
"""
from __future__ import annotations
from datetime import date, datetime
from math import log, sqrt
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from market_predict.models import OptionsWall


def _bsm_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * sqrt(T)))


def _filter_by_strike(df: pd.DataFrame, low: float, high: float) -> pd.DataFrame:
    return df[(df.strike >= low) & (df.strike <= high)].copy()


def compute_wall(
    spot: float,
    expiry_str: str,
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    r: float = 0.04,
) -> Optional[OptionsWall]:
    expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    T = max((expiry - date.today()).days, 1) / 365

    calls = _filter_by_strike(calls, spot * 0.75, spot * 1.25)
    puts = _filter_by_strike(puts, spot * 0.75, spot * 1.25)
    # Drop rows with no real OI: the chain lists every strike, but far strikes
    # legitimately carry OI=0. Without this filter we could pick a zero-OI strike
    # as the "wall" and display $0 OI — actively misleading.
    calls = calls[calls.openInterest > 0]
    puts = puts[puts.openInterest > 0]
    if len(calls) == 0 or len(puts) == 0:
        return None

    # Near-the-money walls (tradable, not crash hedges). If nothing within ±8%,
    # the chain is effectively dead in this band — better to abort than report
    # a deep-OTM crash-hedge strike as a tradable wall.
    calls_near = _filter_by_strike(calls, spot * 0.92, spot * 1.08)
    puts_near = _filter_by_strike(puts, spot * 0.92, spot * 1.08)
    if len(calls_near) == 0 and len(puts_near) == 0:
        return None
    call_wall_row = (calls_near if len(calls_near) else calls).loc[
        (calls_near if len(calls_near) else calls).openInterest.idxmax()
    ]
    put_wall_row = (puts_near if len(puts_near) else puts).loc[
        (puts_near if len(puts_near) else puts).openInterest.idxmax()
    ]

    # Max pain
    strikes = sorted(set(calls.strike) | set(puts.strike))
    pain = []
    for s in strikes:
        call_loss = (calls.openInterest * (s - calls.strike).clip(lower=0)).sum()
        put_loss = (puts.openInterest * (puts.strike - s).clip(lower=0)).sum()
        pain.append((s, call_loss + put_loss))
    max_pain = min(pain, key=lambda x: x[1])[0]

    # ATM IV (from nearest call)
    atm_call = calls.iloc[(calls.strike - spot).abs().argmin()]
    sigma = float(atm_call.impliedVolatility) if atm_call.impliedVolatility > 0 else 0.20

    # Gamma flip via zero crossing
    test_spots = np.linspace(spot * 0.9, spot * 1.1, 41)
    net_gex = []
    for s in test_spots:
        call_gex = sum(
            row.openInterest * _bsm_gamma(s, row.strike, T, r, sigma) * 100 * s * s * 0.01
            for _, row in calls.iterrows()
        )
        put_gex = sum(
            -row.openInterest * _bsm_gamma(s, row.strike, T, r, sigma) * 100 * s * s * 0.01
            for _, row in puts.iterrows()
        )
        net_gex.append((float(s), call_gex + put_gex))

    gamma_flip = None
    for i in range(len(net_gex) - 1):
        if net_gex[i][1] * net_gex[i + 1][1] < 0:
            s0, g0 = net_gex[i]
            s1, g1 = net_gex[i + 1]
            gamma_flip = s0 - g0 * (s1 - s0) / (g1 - g0)
            break

    return OptionsWall(
        expiry=expiry,
        call_wall_strike=float(call_wall_row.strike),
        call_wall_oi=int(call_wall_row.openInterest),
        put_wall_strike=float(put_wall_row.strike),
        put_wall_oi=int(put_wall_row.openInterest),
        max_pain=float(max_pain),
        gamma_flip=float(gamma_flip) if gamma_flip is not None else None,
        total_call_oi=int(calls.openInterest.sum()),
        total_put_oi=int(puts.openInterest.sum()),
        atm_iv=float(sigma),
    )
