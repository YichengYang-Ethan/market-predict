"""Today's setup: synthesize the page's signals into one read.

Pure function of TickerView fields already present in the snapshot — no new
data source. Produces a short regime tag, a one-sentence verdict, and a few
objective breakdown lines. Deliberately descriptive (what the positioning is),
not directional advice.

Gamma convention matches transforms.walls (dealers long calls / short puts):
spot above the γ-flip → net long gamma (dealers hedge against moves, vol-
dampening); spot below → net short gamma (hedging amplifies moves).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Setup:
    tag: str                                   # short regime label
    verdict: str                               # one-sentence synthesis
    lines: list[str] = field(default_factory=list)   # objective breakdown bullets


def _pct(spot: float, level: Optional[float]) -> Optional[float]:
    return (level - spot) / spot * 100 if spot and level else None


def build_setup(view) -> Optional[Setup]:
    """Read the existing TickerView into a setup summary, or None if no spot."""
    spot = getattr(view, "spot", None)
    if not spot:
        return None

    w = getattr(view, "options_wall", None)
    wall_ok = w is not None and (getattr(w, "call_wall_oi", 0) > 0 or getattr(w, "put_wall_oi", 0) > 0)
    lines: list[str] = []
    tags: list[str] = []

    # 1) Gamma regime — the headline for an index-options setup
    if wall_ok and w.gamma_flip:
        gf = w.gamma_flip
        d = _pct(spot, gf)
        if spot >= gf:
            tags.append("positive-gamma")
            lines.append(
                f"**Gamma:** spot ${spot:.0f} is **above** the γ-flip ${gf:.0f} ({d:+.1f}%) "
                f"→ dealers net **long** gamma, **vol-dampening** (dips bought / rips sold, mean-reverting)."
            )
        else:
            tags.append("negative-gamma")
            lines.append(
                f"**Gamma:** spot ${spot:.0f} is **below** the γ-flip ${gf:.0f} ({d:+.1f}%) "
                f"→ dealers net **short** gamma, **vol-amplifying** (hedging chases the move, breakout-prone)."
            )

    # 2) Walls / pin
    if wall_ok:
        up, dn = _pct(spot, w.call_wall_strike), _pct(spot, w.put_wall_strike)
        lines.append(
            f"**Walls:** support put wall ${w.put_wall_strike:.0f} ({dn:+.1f}%) · "
            f"resistance call wall ${w.call_wall_strike:.0f} ({up:+.1f}%) · max-pain ${w.max_pain:.0f}."
        )
        mp_d = _pct(spot, w.max_pain)
        if mp_d is not None and abs(mp_d) <= 0.5:
            tags.append("pinned to max-pain")

    # 3) Positioning (P/C OI) + IV
    if wall_ok and w.total_call_oi:
        pc = w.total_put_oi / max(w.total_call_oi, 1)
        sent = "put-heavy (defensive/hedged)" if pc > 1.1 else (
            "call-heavy (offensive)" if pc < 0.7 else "balanced")
        lines.append(f"**Positioning:** P/C OI {pc:.2f} — {sent}; ATM IV {w.atm_iv * 100:.1f}%.")

    # 4) Vol regime
    vix = getattr(view, "vix", None)
    if vix is not None:
        rel = vix.current - vix.mean_30d
        state = "elevated" if rel > 1 else ("calm" if rel < -1 else "neutral")
        lines.append(f"**Vol:** VIX {vix.current:.1f} ({rel:+.1f} vs 1m avg) — {state}.")

    # 5) Market-implied direction
    p_up = None
    ud = getattr(view, "polymarket_daily_updown", None)
    if ud is not None:
        p_up = ud.p_up
        lines.append(f"**Market-implied:** P(close up) {p_up * 100:.0f}% (Polymarket).")

    tag = " · ".join(dict.fromkeys(tags)) or "neutral"

    # One-line verdict
    bits: list[str] = []
    if wall_ok and w.gamma_flip:
        bits.append("dealers stabilizing (long γ)" if spot >= w.gamma_flip
                    else "dealers destabilizing (short γ)")
    if wall_ok:
        bits.append(f"bracketed put ${w.put_wall_strike:.0f} / call ${w.call_wall_strike:.0f}")
    if vix is not None:
        bits.append(f"VIX {vix.current:.0f}")
    if p_up is not None:
        bits.append(f"{p_up * 100:.0f}% implied up")
    verdict = " · ".join(bits) if bits else "Insufficient options/vol data for a setup read."

    return Setup(tag=tag[:1].upper() + tag[1:], verdict=verdict, lines=lines)
