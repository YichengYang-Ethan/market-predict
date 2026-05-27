"""Plotly figures consumed by the Streamlit app.

Each function takes the TickerView dataclass (or a slice of it) and returns a
plotly Figure. Common style is applied via the COLORS palette and
_apply_theme() helper so all charts share font / margins / template.

Color convention (deliberate, do not change without updating all charts):
    - up / call OI / positive return: green
    - down / put OI / negative return: red
    - spot price: blue (vline / hline)
    - call wall: green dashed
    - put wall: red dashed
    - max pain: gray dotted (distinct from Kalshi purple)
    - gamma flip: orange dotted
    - Kalshi data series: purple
    - Polymarket data series: gold
    - VIX line: violet
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from plotly.subplots import make_subplots

from market_predict.models import KalshiBracket, TickerView


COLORS = {
    "up": "#27ae60",
    "down": "#c0392b",
    "spot": "#2980b9",
    "call_wall": "#16a085",
    "put_wall": "#c0392b",
    "max_pain": "#7f8c8d",
    "gamma_flip": "#d35400",
    "kalshi": "#8e44ad",
    "kalshi_fill": "rgba(142, 68, 173, 0.55)",
    "polymarket": "#f39c12",
    "polymarket_fill": "rgba(243, 156, 18, 0.55)",
    "vix": "#8e44ad",
    "neutral_text": "#2c3e50",
    "grid": "rgba(0,0,0,0.06)",
}


def _apply_theme(fig: go.Figure, *, title: str | None = None, height: int = 380) -> go.Figure:
    """Apply a unified style: white template, compact margins, consistent fonts."""
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, font=dict(size=14, color=COLORS["neutral_text"])) if title else None,
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size=12),
        height=height,
        margin=dict(t=60 if title else 30, b=40, l=50, r=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font_size=11),
        xaxis=dict(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"]),
        yaxis=dict(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"]),
    )
    return fig


# ─────────────────────── price history (candle + volume) ───────────


def price_history(view: TickerView) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.03,
    )
    df = view.history
    if df is None or df.empty:
        fig.update_layout(title=f"{view.symbol} — no history")
        return fig

    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            name=view.symbol,
            increasing_line_color=COLORS["up"],
            decreasing_line_color=COLORS["down"],
            showlegend=False,
        ),
        row=1, col=1,
    )

    colors = [
        f"rgba(39, 174, 96, 0.45)" if c >= o else "rgba(192, 57, 43, 0.45)"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(
        go.Bar(x=df.index, y=df["Volume"], marker_color=colors, name="Vol", showlegend=False),
        row=2, col=1,
    )

    fig.add_hline(
        y=view.spot, line_color=COLORS["spot"], line_dash="dot", line_width=1,
        annotation_text=f"spot ${view.spot:.2f}", annotation_position="right",
        annotation_font_size=10, annotation_font_color=COLORS["spot"],
        row=1, col=1,
    )

    n_days = len(df)
    high_3mo = df["High"].max()
    low_3mo = df["Low"].min()
    pct_in_range = (view.spot - low_3mo) / (high_3mo - low_3mo) * 100 if high_3mo > low_3mo else 50

    title = (
        f"{view.symbol} · {n_days}d history · "
        f"3mo range ${low_3mo:.2f}–${high_3mo:.2f} · "
        f"spot at {pct_in_range:.0f}% of range"
    )
    _apply_theme(fig, title=title, height=380)
    fig.update_layout(xaxis_rangeslider_visible=False, showlegend=False)
    fig.update_yaxes(title_text="Price", row=1, col=1, gridcolor=COLORS["grid"])
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor=COLORS["grid"])
    return fig


# ─────────────────────────── VIX mini ───────────────────────────────


def vix_mini(view: TickerView) -> go.Figure:
    fig = go.Figure()
    if view.vix is None or view.vix.history_30d.empty:
        return _apply_theme(fig, title="VIX — no data", height=200)

    df = view.vix.history_30d
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], mode="lines",
        line=dict(color=COLORS["vix"], width=2),
        fill="tozeroy",
        fillcolor="rgba(142, 68, 173, 0.08)",
        name="VIX",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>",
    ))
    fig.add_hline(
        y=view.vix.mean_30d, line_color="rgba(0,0,0,0.35)", line_dash="dash", line_width=1,
        annotation_text=f"1m avg {view.vix.mean_30d:.1f}",
        annotation_position="right", annotation_font_size=10,
    )
    for level in (15, 20, 30):
        fig.add_hline(y=level, line_color="rgba(0,0,0,0.10)", line_dash="dot", line_width=0.5)

    _apply_theme(fig, title=f"VIX 1m · current {view.vix.current:.2f}", height=200)
    fig.update_layout(showlegend=False, yaxis_title=None, margin=dict(t=40, b=20, l=40, r=20))
    return fig


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
        name="Call OI", marker_color="rgba(39, 174, 96, 0.65)",
        hovertemplate="Strike $%{x:.0f}<br>Call OI %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=puts.strike, y=-puts.openInterest,
        name="Put OI (−)", marker_color="rgba(192, 57, 43, 0.65)",
        hovertemplate="Strike $%{x:.0f}<br>Put OI %{y:,.0f}<extra></extra>",
    ))

    w = view.options_wall
    # Alternate annotation position (top / bottom) so labels don't overlap
    levels = [
        (spot, f"spot ${spot:.0f}", COLORS["spot"], "solid", "top"),
        (w.call_wall_strike, f"call wall ${w.call_wall_strike:.0f}", COLORS["call_wall"], "dash", "top right"),
        (w.put_wall_strike, f"put wall ${w.put_wall_strike:.0f}", COLORS["put_wall"], "dash", "top left"),
        (w.max_pain, f"max pain ${w.max_pain:.0f}", COLORS["max_pain"], "dot", "bottom"),
    ]
    if w.gamma_flip:
        levels.append((w.gamma_flip, f"γ flip ${w.gamma_flip:.0f}", COLORS["gamma_flip"], "dot", "bottom right"))

    for x, text, color, dash, pos in levels:
        fig.add_vline(
            x=x, line_color=color, line_dash=dash, line_width=1.5,
            annotation_text=text, annotation_position=pos,
            annotation_font_size=10, annotation_font_color=color,
        )

    title = (
        f"Options walls · expiry {w.expiry} "
        f"({(w.expiry - pd.Timestamp.today().date()).days}d) · "
        f"ATM IV {w.atm_iv*100:.1f}%"
    )
    _apply_theme(fig, title=title, height=400)
    fig.update_layout(
        barmode="relative",
        xaxis_title="Strike ($)",
        yaxis_title="Open Interest (call + / put −)",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
    )
    return fig


# ─────────────────────── Kalshi distribution ────────────────────────


def kalshi_distribution(
    brackets: list[KalshiBracket],
    ref_value: float,
    ref_name: str,
    title: str,
) -> go.Figure:
    fig = go.Figure()
    if not brackets:
        fig.update_layout(title=f"{title} — no active brackets")
        return fig

    between = sorted(
        [b for b in brackets if b.kind == "between"],
        key=lambda b: (b.strike_low + b.strike_high) / 2,
    )
    below_rails = sorted(
        [b for b in brackets if b.kind == "below"],
        key=lambda b: b.strike_high or 0,
        reverse=True,
    )
    above_rails = sorted(
        [b for b in brackets if b.kind == "above"],
        key=lambda b: b.strike_low or 0,
    )

    if between:
        xs = [(b.strike_low + b.strike_high) / 2 for b in between]
        ys = [b.yes_mid * 100 for b in between]
        labels = [
            f"{b.strike_low:,.0f}–{b.strike_high:,.0f}<br>OI {b.open_interest:,.0f} ctrs<br>vol24 ${b.volume_24h:,.0f}"
            for b in between
        ]
        bar_width = (between[0].strike_high - between[0].strike_low) * 0.85 if len(between) else None
        fig.add_trace(go.Bar(
            x=xs, y=ys, width=bar_width,
            customdata=labels,
            hovertemplate="%{customdata}<br>P = %{y:.1f}%<extra></extra>",
            marker_color=COLORS["kalshi_fill"],
            name="P(close in bucket)",
        ))

    max_y = max([b.yes_mid * 100 for b in between], default=10)

    if below_rails:
        b = below_rails[0]
        fig.add_annotation(
            x=b.strike_high, y=max_y * 0.9,
            text=f"<b>P(<{b.strike_high:,.0f}) = {b.yes_mid*100:.1f}%</b>",
            showarrow=True, arrowhead=2, arrowcolor=COLORS["down"], ax=-40, ay=-30,
            font=dict(color=COLORS["down"], size=11),
        )
    if above_rails:
        b = above_rails[0]
        fig.add_annotation(
            x=b.strike_low, y=max_y * 0.9,
            text=f"<b>P(>{b.strike_low:,.0f}) = {b.yes_mid*100:.1f}%</b>",
            showarrow=True, arrowhead=2, arrowcolor=COLORS["up"], ax=40, ay=-30,
            font=dict(color=COLORS["up"], size=11),
        )

    if ref_value:
        fig.add_vline(
            x=ref_value, line_color=COLORS["spot"], line_dash="solid", line_width=2,
            annotation_text=f"<b>{ref_name} {ref_value:,.0f}</b>",
            annotation_position="top", annotation_font_color=COLORS["spot"],
        )

    _apply_theme(fig, title=title, height=400)
    fig.update_layout(
        xaxis_title=ref_name,
        yaxis_title="Probability (%)",
        showlegend=False,
    )
    return fig


# ─────────────────── Polymarket one-touch ───────────────────────────


def polymarket_one_touch(poly_event, ref_value: float, ref_name: str) -> go.Figure:
    """Two-line chart: P(HIGH touched) and P(LOW touched) by strike.

    Path-dependent one-touch — NOT a distribution. Each strike is its own bet.
    """
    fig = go.Figure()
    if poly_event is None or not poly_event.brackets:
        return _apply_theme(fig, title="Polymarket — no contracts for this underlying", height=400)

    high = sorted([b for b in poly_event.brackets if b.direction == "HIGH"], key=lambda b: b.strike)
    low = sorted([b for b in poly_event.brackets if b.direction == "LOW"], key=lambda b: b.strike, reverse=True)

    if high:
        fig.add_trace(go.Scatter(
            x=[b.strike for b in high],
            y=[b.yes_price * 100 for b in high],
            mode="lines+markers",
            name="P(HIGH touched)",
            line=dict(color=COLORS["up"], width=2.5),
            marker=dict(size=10),
            hovertemplate="Strike $%{x:,.0f}<br>P(touch HIGH) = %{y:.1f}%<extra></extra>",
        ))
    if low:
        fig.add_trace(go.Scatter(
            x=[b.strike for b in low],
            y=[b.yes_price * 100 for b in low],
            mode="lines+markers",
            name="P(LOW touched)",
            line=dict(color=COLORS["down"], width=2.5),
            marker=dict(size=10),
            hovertemplate="Strike $%{x:,.0f}<br>P(touch LOW) = %{y:.1f}%<extra></extra>",
        ))

    if ref_value:
        fig.add_vline(
            x=ref_value, line_color=COLORS["spot"], line_dash="solid", line_width=2,
            annotation_text=f"<b>{ref_name} {ref_value:,.0f}</b>",
            annotation_position="top", annotation_font_color=COLORS["spot"],
        )

    _apply_theme(
        fig,
        title=(
            "Polymarket barrier-touch probabilities · "
            "P(touched by expiry) per strike · "
            f"{poly_event.title}"
        ),
        height=400,
    )
    fig.update_layout(
        xaxis_title=ref_name,
        yaxis_title="P(touched by expiry) (%)",
        yaxis_range=[0, 100],
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
    )
    return fig


# ─────────────────── Daily brackets dual source ─────────────────────


def daily_brackets_dual(
    kalshi_brackets,        # list[KalshiBracket] SPX-scale
    poly_close_brackets,    # PolyCloseBracketsEvent or None (SPY-scale cumulative)
    spot: float,            # SPY ETF price
    underlying_value: float,
    underlying_name: str,
    spx_to_spy_ratio: float,
) -> go.Figure:
    """Two-source daily close brackets on a unified SPY-price X-axis.

    Kalshi KXINX brackets (SPX scale) are divided by the live ratio to fit SPY.
    Polymarket cumulative 'closes above' is monotonized then differenced.
    Kalshi brackets are filtered to the soonest-resolving event (KXINX returns
    multiple expiries per call).
    """
    fig = go.Figure()
    if not kalshi_brackets and not poly_close_brackets:
        fig.update_layout(title="Daily close brackets — no data")
        return fig

    # Live SPX/SPY ratio is more accurate than the hardcoded 10.0
    if underlying_value and spot:
        ratio = underlying_value / spot
    else:
        ratio = spx_to_spy_ratio

    # Filter Kalshi brackets to the soonest event (KXINX often returns 2+ expiries)
    kalshi_filtered = kalshi_brackets or []
    if kalshi_filtered:
        next_close = min(b.close_time for b in kalshi_filtered if b.close_time)
        kalshi_filtered = [b for b in kalshi_filtered if b.close_time == next_close]

    # Kalshi → SPY scale (divide strikes by live ratio)
    kalshi_between = [
        b for b in kalshi_filtered
        if b.kind == "between" and b.strike_low and b.strike_high and b.yes_mid > 0
    ]
    if kalshi_between:
        xs = [((b.strike_low + b.strike_high) / 2) / ratio for b in kalshi_between]
        ys = [b.yes_mid * 100 for b in kalshi_between]
        labels = [
            f"Kalshi: {b.strike_low:,.0f}–{b.strike_high:,.0f} (SPX)"
            f"<br>= ${b.strike_low/ratio:.1f}–${b.strike_high/ratio:.1f} (SPY)"
            f"<br>P = {b.yes_mid*100:.1f}%"
            f"<br>OI {b.open_interest:,.0f} ctrs"
            for b in kalshi_between
        ]
        width = (kalshi_between[0].strike_high - kalshi_between[0].strike_low) / ratio * 0.85
        fig.add_trace(go.Bar(
            x=xs, y=ys, width=width,
            customdata=labels,
            hovertemplate="%{customdata}<extra></extra>",
            marker_color=COLORS["kalshi_fill"],
            name="Kalshi brackets",
        ))

    # Polymarket cumulative → monotonize → differenced brackets
    if poly_close_brackets and poly_close_brackets.brackets:
        sb = sorted(poly_close_brackets.brackets, key=lambda b: b.strike)
        # Enforce monotonic-decreasing P from low→high strike. Pass right-to-left:
        # at each strike, P cannot exceed P at any higher strike (cumulative noise fix).
        mono_prices = [b.yes_price for b in sb]
        for i in range(len(mono_prices) - 2, -1, -1):
            if mono_prices[i] < mono_prices[i + 1]:
                mono_prices[i] = mono_prices[i + 1]
        diff_x, diff_y, diff_lbl = [], [], []
        for i in range(len(sb) - 1):
            lo, hi = sb[i].strike, sb[i + 1].strike
            prob = mono_prices[i] - mono_prices[i + 1]
            if prob <= 0.0005:  # < 0.05 pp = noise
                continue
            diff_x.append((lo + hi) / 2)
            diff_y.append(prob * 100)
            diff_lbl.append(
                f"Polymarket: ${lo:.0f}–${hi:.0f}"
                f"<br>P(close in bucket) = {prob * 100:.1f}%"
                f"<br>(monotonized cumulative diff)"
            )
        width_p = (sb[1].strike - sb[0].strike) * 0.85 if len(sb) > 1 else 5
        if diff_x:
            fig.add_trace(go.Bar(
                x=diff_x, y=diff_y, width=width_p,
                customdata=diff_lbl,
                hovertemplate="%{customdata}<extra></extra>",
                marker_color=COLORS["polymarket_fill"],
                name="Polymarket (differenced)",
            ))

    if spot:
        fig.add_vline(
            x=spot, line_color=COLORS["spot"], line_dash="solid", line_width=2,
            annotation_text=f"<b>spot ${spot:.2f}</b>",
            annotation_position="top", annotation_font_color=COLORS["spot"],
        )

    close_date = None
    if poly_close_brackets:
        close_date = poly_close_brackets.end_date
    elif kalshi_filtered:
        close_date = kalshi_filtered[0].close_time

    _apply_theme(fig, title=f"Daily close brackets · resolves {close_date or 'today'}", height=380)
    fig.update_layout(
        xaxis_title=f"{view_symbol_for_axis(underlying_name)} close price",
        yaxis_title="Probability (%)",
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
    )
    return fig


def view_symbol_for_axis(underlying_name: str) -> str:
    """Friendlier axis label: 'S&P 500' → 'SPY', 'Nasdaq 100' → 'QQQ'."""
    mapping = {"S&P 500": "SPY", "Nasdaq 100": "QQQ"}
    return mapping.get(underlying_name, underlying_name)


# ───────────────── Kalshi rate cut count / event outcomes ───────────


def kalshi_event_outcomes_bar(meeting, title: str, color: str | None = None) -> go.Figure:
    """Horizontal bar of outcome probabilities for a Kalshi multi-outcome event.

    The color argument defaults to Kalshi purple. Pass COLORS["polymarket"] when
    rendering a Polymarket-sourced event for consistent venue color coding.
    """
    fig = go.Figure()
    if meeting is None or not meeting.outcomes:
        return _apply_theme(fig, title=f"{title} — no data", height=300)
    if color is None:
        color = COLORS["kalshi"]
    outcomes = sorted(meeting.outcomes, key=lambda o: -o.yes_mid)[:8]
    fig.add_trace(go.Bar(
        y=[o.title for o in outcomes],
        x=[o.yes_mid * 100 for o in outcomes],
        orientation="h",
        text=[f"{o.yes_mid * 100:.0f}%" for o in outcomes],
        textposition="outside",
        marker_color=color,
        hovertemplate="%{y}<br>P = %{x:.1f}%<br>OI %{customdata:,.0f} ctrs<extra></extra>",
        customdata=[o.open_interest for o in outcomes],
    ))
    _apply_theme(fig, title=f"{title} · resolves {meeting.close_time}", height=300)
    fig.update_layout(
        xaxis_title="P (%)",
        yaxis=dict(autorange="reversed"),
        margin=dict(t=50, b=40, l=140, r=40),
        showlegend=False,
    )
    return fig


# ───────────────────────── Recession gauge ──────────────────────────


def recession_gauge(kalshi_recession_list) -> go.Figure:
    """Gauge for KXRECSSNBER — picks the 2026 (current year) event by default."""
    fig = go.Figure()
    if not kalshi_recession_list:
        fig.update_layout(title="Recession — no data")
        return fig

    # Pick the soonest-resolving binary (closest year)
    current = sorted(kalshi_recession_list, key=lambda b: b.close_time)[0]
    p = current.yes_mid * 100

    # Pretty event label: 'KXRECSSNBER-26' → 'NBER recession 2026'
    label = current.event_ticker.replace("KXRECSSNBER-", "")
    if label.isdigit():
        label = f"20{label}" if len(label) == 2 else label

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=p,
        number={"suffix": "%", "font": {"size": 40, "color": COLORS["neutral_text"]}},
        title={"text": f"NBER recession · {label}", "font": {"size": 14, "color": COLORS["neutral_text"]}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": COLORS["neutral_text"]},
            "bar": {"color": COLORS["down"] if p > 30 else (COLORS["gamma_flip"] if p > 15 else COLORS["up"])},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 15], "color": "rgba(39, 174, 96, 0.15)"},
                {"range": [15, 30], "color": "rgba(241, 196, 15, 0.18)"},
                {"range": [30, 100], "color": "rgba(192, 57, 43, 0.15)"},
            ],
            "threshold": {
                "line": {"color": COLORS["spot"], "width": 3},
                "thickness": 0.75,
                "value": 16.5,  # historical 16.5% base rate
            },
        },
    ))
    fig.update_layout(
        height=280,
        margin=dict(t=40, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ───────────────────────── Mag 7 ranking ────────────────────────────


def mag7_ranking_bar(poly_largest_event) -> go.Figure:
    """Horizontal bar of 'Will [company] be largest?' probabilities, gradient-colored."""
    fig = go.Figure()
    if poly_largest_event is None or not poly_largest_event.rows:
        return _apply_theme(fig, title="Largest company — no data", height=340)

    rows = poly_largest_event.rows[:10]
    # Gradient from darker (highest probability) to lighter
    max_p = max((r.yes_price for r in rows), default=1) or 1
    colors_list = []
    for r in rows:
        intensity = 0.35 + 0.55 * (r.yes_price / max_p)  # 0.35 ~ 0.90
        colors_list.append(f"rgba(243, 156, 18, {intensity:.2f})")

    fig.add_trace(go.Bar(
        y=[r.name for r in rows],
        x=[r.yes_price * 100 for r in rows],
        orientation="h",
        text=[f"{r.yes_price * 100:.1f}%" for r in rows],
        textposition="outside",
        marker_color=colors_list,
        marker_line=dict(color=COLORS["polymarket"], width=1),
        hovertemplate="%{y}<br>P(largest) = %{x:.1f}%<br>vol24 $%{customdata:,.0f}<extra></extra>",
        customdata=[r.volume_24h for r in rows],
    ))
    _apply_theme(fig, title=f"{poly_largest_event.title} · Polymarket", height=340)
    fig.update_layout(
        xaxis_title="P(largest company) %",
        yaxis=dict(autorange="reversed"),
        margin=dict(t=50, b=40, l=80, r=60),
        showlegend=False,
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

    palette = {
        "hold": "#95a5a6",
        "maintain": "#95a5a6",
        "cut": COLORS["spot"],
        "hike": COLORS["down"],
    }
    def color_for(label: str) -> str:
        low = label.lower()
        for key, color in palette.items():
            if key in low:
                return color
        return "#bdc3c7"

    for outcome in df["outcome"].unique():
        sub = df[df["outcome"] == outcome]
        fig.add_trace(go.Bar(
            y=sub["meeting"], x=sub["prob"],
            name=outcome, orientation="h",
            marker_color=color_for(outcome),
            text=[f"{p:.0f}%" if p >= 5 else "" for p in sub["prob"]],
            textposition="inside",
            insidetextfont=dict(color="white", size=11),
            hovertemplate=f"{outcome}<br>%{{x:.1f}}%<br>OI %{{customdata:,.0f}} ctrs<extra></extra>",
            customdata=sub["oi"],
        ))

    _apply_theme(fig, title="Fed path · next FOMC meetings (Kalshi)", height=300)
    fig.update_layout(
        barmode="stack",
        xaxis_title="Probability (%)",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5, font=dict(size=10)),
        margin=dict(t=50, b=70, l=110, r=20),
    )
    return fig
