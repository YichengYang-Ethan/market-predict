"""Plain-text CLI renderer for TickerView."""
from __future__ import annotations
from datetime import date, datetime

from market_predict.models import TickerView


def render(view: TickerView) -> None:
    print(f"\n{'━' * 70}")
    print(
        f"  {view.symbol}  ${view.spot:.2f}   "
        f"{view.underlying_name} ({view.underlying_value:,.2f})   "
        f"{view.timestamp:%Y-%m-%d %H:%M}"
    )
    print(f"{'━' * 70}")

    _render_walls(view)
    _render_kalshi(view)
    _render_fed(view)
    print()


def _render_walls(view: TickerView) -> None:
    w = view.options_wall
    if not w:
        print("  Options: no chain data available")
        return
    days_out = (w.expiry - date.today()).days
    print(f"\n  Options walls (expiry {w.expiry}, {days_out}d):")
    print(f"    Call wall:    ${w.call_wall_strike:.0f}  ({w.call_wall_oi:,} OI)")
    print(f"    Put wall:     ${w.put_wall_strike:.0f}  ({w.put_wall_oi:,} OI)")
    print(f"    Max pain:     ${w.max_pain:.0f}")
    if w.gamma_flip is not None:
        print(f"    Gamma flip:   ${w.gamma_flip:.0f}")
    else:
        print(f"    Gamma flip:   (no zero crossing in ±10% range)")
    print(f"    ATM IV:       {w.atm_iv * 100:.1f}%")
    pc = w.total_put_oi / max(w.total_call_oi, 1)
    print(
        f"    Total OI:     {w.total_call_oi:,} call / {w.total_put_oi:,} put  "
        f"(P/C={pc:.2f})"
    )


def _render_kalshi(view: TickerView) -> None:
    brackets = view.kalshi_yearly
    if not brackets:
        print("\n  Kalshi distribution: (no active brackets)")
        return

    close_time = brackets[0].close_time
    ref = view.underlying_value
    days_out = (datetime.strptime(close_time, "%Y-%m-%d").date() - date.today()).days
    print(
        f"\n  Kalshi {view.underlying_name} distribution "
        f"(resolve {close_time}, {days_out}d):"
    )

    def sort_key(b):
        if b.kind == "above":
            return b.strike_low or 0
        if b.kind == "below":
            return b.strike_high or 0
        if b.kind == "between":
            return (b.strike_low + b.strike_high) / 2
        return 0

    below_rails = [b for b in brackets if b.kind == "below"]
    above_rails = [b for b in brackets if b.kind == "above"]
    between = sorted([b for b in brackets if b.kind == "between"], key=sort_key)
    between_near = sorted(between, key=lambda b: abs(sort_key(b) - ref))[:7]
    between_near = sorted(between_near, key=sort_key)

    rows = []
    if below_rails:
        rows.append(max(below_rails, key=lambda b: b.strike_high or 0))
    rows.extend(between_near)
    if above_rails:
        rows.append(min(above_rails, key=lambda b: b.strike_low or 0))

    prob_sum = sum(b.yes_mid for b in rows)
    for b in rows:
        if b.kind == "below":
            label = f"<{b.strike_high:,.0f}"
        elif b.kind == "above":
            label = f">{b.strike_low:,.0f}"
        else:
            label = f"{b.strike_low:,.0f}-{b.strike_high:,.0f}"
        marker = "  ← spot" if (b.kind == "between" and b.strike_low <= ref <= b.strike_high) else ""
        print(
            f"    P({label:>16s}) = {b.yes_mid*100:5.1f}%  "
            f"(OI ${b.open_interest:>9,.0f}, vol24 ${b.volume_24h:>6,.0f}){marker}"
        )
    print(
        f"    {'shown coverage':>16s}   {prob_sum*100:5.1f}% "
        f"(rest of distribution outside displayed range)"
    )


def _render_fed(view: TickerView) -> None:
    if not view.fed_meetings:
        print("\n  Fed path: (no data)")
        return
    print(f"\n  Fed path (next {len(view.fed_meetings)} FOMC meetings):")
    for meeting in view.fed_meetings:
        print(f"    {meeting.event_ticker} (close {meeting.close_time}):")
        for o in sorted(meeting.outcomes, key=lambda x: -x.yes_mid)[:4]:
            print(
                f"      {o.title[:50]:50s} = {o.yes_mid * 100:5.1f}%  "
                f"(OI ${o.open_interest:,.0f})"
            )
