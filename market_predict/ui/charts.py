"""Plotly figures consumed by the Streamlit app.

Three charts, one per top-level concept:
    - options_wall: call/put OI bars around spot, with vlines for key levels
    - kalshi_distribution: probability histogram across yearly brackets
    - fed_path: horizontal stacked bars for the next FOMC meetings

Each function takes the TickerView dataclass and returns a plotly Figure.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go

from market_predict.models import TickerView

if TYPE_CHECKING:
    pass


# ─────────────────────────── options wall ───────────────────────────


def options_wall(view: TickerView) -> go.Figure:
    fig = go.Figure()
    if view.calls_chain is None or view.puts_chain is None or view.options_wall is None:
        fig.update_layout(title="No options chain available")
        return fig

    spot = view.spot
    lo, hi = spot * 0.85, spot * 1.15
    calls = view.calls_chain[(view.calls_chain.strike >= lo) & (view.calls_chain.strike <= hi)]
    puts = view.puts_chain[(view.puts_chain.strike >= lo) & (view.puts_chain.strike <= hi)]

    fig.add_trace(go.Bar(
        x=calls.strike, y=calls.openInterest,
        name="Call OI", marker_color="rgba(46, 204, 113, 0.7)",
        hovertemplate="Strike $%{x:.0f}<br>Call OI %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=puts.strike, y=-puts.openInterest,
        name="Put OI (negative)", marker_color="rgba(231, 76, 60, 0.7)",
        hovertemplate="Strike $%{x:.0f}<br>Put OI %{y:,.0f}<extra></extra>",
    ))

    w = view.options_wall
    levels = [
        (spot, "spot", "#3498db", "solid"),
        (w.call_wall_strike, f"call wall ${w.call_wall_strike:.0f}", "#27ae60", "dash"),
        (w.put_wall_strike, f"put wall ${w.put_wall_strike:.0f}", "#c0392b", "dash"),
        (w.max_pain, f"max pain ${w.max_pain:.0f}", "#9b59b6", "dot"),
    ]
    if w.gamma_flip:
        levels.append((w.gamma_flip, f"γ flip ${w.gamma_flip:.0f}", "#f39c12", "dot"))

    for x, text, color, dash in levels:
        fig.add_vline(
            x=x, line_color=color, line_dash=dash, line_width=1.5,
            annotation_text=text, annotation_position="top",
            annotation_font_size=10, annotation_font_color=color,
        )

    fig.update_layout(
        title=f"Options walls — expiry {w.expiry} ({(w.expiry - pd.Timestamp.today().date()).days}d)  |  ATM IV {w.atm_iv*100:.1f}%",
        barmode="relative",
        height=400,
        xaxis_title="Strike ($)",
        yaxis_title="Open Interest (call+ / put−)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=70, b=40, l=50, r=20),
    )
    return fig


# ─────────────────────── Kalshi distribution ────────────────────────


def kalshi_distribution(view: TickerView) -> go.Figure:
    fig = go.Figure()
    if not view.kalshi_yearly:
        fig.update_layout(title="No Kalshi brackets available")
        return fig

    between = sorted(
        [b for b in view.kalshi_yearly if b.kind == "between"],
        key=lambda b: (b.strike_low + b.strike_high) / 2,
    )
    below_rails = sorted(
        [b for b in view.kalshi_yearly if b.kind == "below"],
        key=lambda b: b.strike_high or 0,
        reverse=True,
    )
    above_rails = sorted(
        [b for b in view.kalshi_yearly if b.kind == "above"],
        key=lambda b: b.strike_low or 0,
    )

    if between:
        xs = [(b.strike_low + b.strike_high) / 2 for b in between]
        ys = [b.yes_mid * 100 for b in between]
        labels = [
            f"{b.strike_low:,.0f}–{b.strike_high:,.0f}<br>OI ${b.open_interest:,.0f}<br>vol24 ${b.volume_24h:,.0f}"
            for b in between
        ]
        bar_width = (between[0].strike_high - between[0].strike_low) * 0.9 if len(between) else None
        fig.add_trace(go.Bar(
            x=xs, y=ys, width=bar_width,
            customdata=labels,
            hovertemplate="%{customdata}<br>P = %{y:.1f}%<extra></extra>",
            marker_color="rgba(52, 152, 219, 0.75)",
            name="P(strike-bucket)",
        ))

    max_y = max([b.yes_mid * 100 for b in between], default=10)

    if below_rails:
        b = below_rails[0]
        fig.add_annotation(
            x=b.strike_high, y=max_y * 0.9,
            text=f"<b>P(<{b.strike_high:,.0f}) = {b.yes_mid*100:.1f}%</b>",
            showarrow=True, arrowhead=2, arrowcolor="#c0392b", ax=-40, ay=-30,
            font=dict(color="#c0392b"),
        )
    if above_rails:
        b = above_rails[0]
        fig.add_annotation(
            x=b.strike_low, y=max_y * 0.9,
            text=f"<b>P(>{b.strike_low:,.0f}) = {b.yes_mid*100:.1f}%</b>",
            showarrow=True, arrowhead=2, arrowcolor="#27ae60", ax=40, ay=-30,
            font=dict(color="#27ae60"),
        )

    fig.add_vline(
        x=view.underlying_value, line_color="#2c3e50", line_dash="solid", line_width=2,
        annotation_text=f"<b>{view.underlying_name} {view.underlying_value:,.0f}</b>",
        annotation_position="top",
    )

    close_time = view.kalshi_yearly[0].close_time
    fig.update_layout(
        title=f"Kalshi {view.underlying_name} distribution — resolves {close_time}",
        xaxis_title=view.underlying_name,
        yaxis_title="Probability (%)",
        height=400,
        showlegend=False,
        margin=dict(t=70, b=40, l=50, r=20),
    )
    return fig


# ─────────────────────────── Fed path ───────────────────────────────


def fed_path(view: TickerView) -> go.Figure:
    fig = go.Figure()
    if not view.fed_meetings:
        fig.update_layout(title="No Fed data")
        return fig

    rows = []
    for meeting in view.fed_meetings:
        label = meeting.event_ticker.replace("KXFEDDECISION-", "") + f" ({meeting.close_time})"
        for o in meeting.outcomes:
            rows.append({
                "meeting": label,
                "outcome": o.title[:40],
                "prob": o.yes_mid * 100,
                "oi": o.open_interest,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return fig

    # Stable color per outcome label
    palette = {
        "hold": "#7f8c8d",
        "maintain": "#7f8c8d",
        "cut": "#3498db",
        "hike": "#e74c3c",
    }
    def color_for(label: str) -> str:
        low = label.lower()
        for key, color in palette.items():
            if key in low:
                return color
        return "#95a5a6"

    for outcome in df["outcome"].unique():
        sub = df[df["outcome"] == outcome]
        fig.add_trace(go.Bar(
            y=sub["meeting"], x=sub["prob"],
            name=outcome, orientation="h",
            marker_color=color_for(outcome),
            text=[f"{p:.0f}%" if p >= 5 else "" for p in sub["prob"]],
            textposition="inside",
            hovertemplate=f"{outcome}<br>%{{x:.1f}}%<br>OI $%{{customdata:,.0f}}<extra></extra>",
            customdata=sub["oi"],
        ))

    fig.update_layout(
        title="Fed path — next FOMC meetings (Kalshi KXFEDDECISION)",
        barmode="stack",
        height=300,
        xaxis_title="Probability (%)",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
        margin=dict(t=50, b=60, l=80, r=20),
    )
    return fig
