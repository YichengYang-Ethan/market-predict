"""Streamlit entry: visual dashboard for a single ticker view.

Run locally:
    streamlit run streamlit_app.py

Deploy: connect this repo to share.streamlit.io and it just works.
"""
from __future__ import annotations

import streamlit as st

from market_predict.cli import build_view
from market_predict.tickers import TICKER_MAP
from market_predict.ui import charts


st.set_page_config(page_title="market-predict", page_icon="📊", layout="wide")


# ─────────────────────── cache layer ───────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def load_view(symbol: str):
    """5-minute TTL keeps Streamlit Cloud from spamming yfinance / Kalshi."""
    return build_view(symbol)


# ─────────────────────────── UI ───────────────────────────


st.title("📊 market-predict")
st.caption(
    "Ticker context: spot + options walls + Kalshi prediction-market distribution + Fed path. "
    "All data sources are free and public (no auth)."
)

# Top controls
ctrl_l, ctrl_r = st.columns([4, 1])
with ctrl_l:
    symbol = st.selectbox(
        "Ticker", list(TICKER_MAP.keys()), index=0, label_visibility="collapsed"
    )
with ctrl_r:
    if st.button("🔄 Refresh", use_container_width=True):
        load_view.clear()
        st.rerun()

# Fetch
with st.spinner(f"Fetching {symbol} data..."):
    try:
        view = load_view(symbol)
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        st.stop()

# Header metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric(view.symbol, f"${view.spot:.2f}")
m2.metric(view.underlying_name, f"{view.underlying_value:,.2f}")
if view.options_wall:
    m3.metric("ATM IV", f"{view.options_wall.atm_iv * 100:.1f}%")
    pc = view.options_wall.total_put_oi / max(view.options_wall.total_call_oi, 1)
    m4.metric("Put/Call OI", f"{pc:.2f}")

st.divider()

# Options walls
st.subheader("Options walls")
if view.options_wall:
    st.plotly_chart(charts.options_wall(view), use_container_width=True)
    w = view.options_wall
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Call wall", f"${w.call_wall_strike:.0f}", f"{w.call_wall_oi:,} OI")
    c2.metric("Put wall", f"${w.put_wall_strike:.0f}", f"{w.put_wall_oi:,} OI")
    c3.metric("Max pain", f"${w.max_pain:.0f}")
    c4.metric(
        "Gamma flip",
        f"${w.gamma_flip:.0f}" if w.gamma_flip is not None else "n/a",
    )
else:
    st.info("No options chain available for this ticker.")

# Two-column: Kalshi distribution + Fed path
col_l, col_r = st.columns([1, 1])
with col_l:
    st.subheader("Kalshi distribution")
    st.plotly_chart(charts.kalshi_distribution(view), use_container_width=True)
with col_r:
    st.subheader("Fed path")
    st.plotly_chart(charts.fed_path(view), use_container_width=True)

st.divider()

# Auto-generated narrative notes
with st.expander("💡 Reading notes (auto-generated)"):
    notes = []
    if view.options_wall:
        w = view.options_wall
        if w.call_wall_strike < view.spot:
            notes.append(
                f"**Call wall below spot** — most call OI concentrated at "
                f"${w.call_wall_strike:.0f}, which sits ${view.spot - w.call_wall_strike:.0f} "
                f"({(view.spot - w.call_wall_strike) / view.spot * 100:.1f}%) below current price. "
                f"This is unusual; check whether it reflects ITM positions vs. true resistance."
            )
        if w.put_wall_strike < view.spot * 0.95:
            notes.append(
                f"**Put wall {(view.spot - w.put_wall_strike) / view.spot * 100:.1f}% below spot** "
                f"at ${w.put_wall_strike:.0f} — typical crash-hedge zone."
            )
        pc = w.total_put_oi / max(w.total_call_oi, 1)
        if pc > 1.5:
            notes.append(f"**P/C ratio {pc:.2f}** — heavily hedged book.")
        elif pc < 0.7:
            notes.append(f"**P/C ratio {pc:.2f}** — call-heavy, complacent positioning.")
        if w.gamma_flip is not None:
            dist = (w.gamma_flip - view.spot) / view.spot * 100
            notes.append(
                f"**Gamma flip at ${w.gamma_flip:.0f}** ({dist:+.1f}% from spot) — "
                f"dealer hedging sign change near current level."
            )

    if view.fed_meetings:
        next_m = view.fed_meetings[0]
        hold = next((o for o in next_m.outcomes if "maintain" in o.title.lower() or "hold" in o.title.lower()), None)
        if hold:
            notes.append(
                f"**Next FOMC ({next_m.close_time})**: P(hold) = {hold.yes_mid * 100:.1f}% — "
                f"{'tight consensus' if hold.yes_mid > 0.85 else 'meaningful uncertainty'}."
            )

    if notes:
        for n in notes:
            st.markdown(f"- {n}")
    else:
        st.write("(no notable patterns detected)")

st.caption(
    f"Last fetch: {view.timestamp:%Y-%m-%d %H:%M}  ·  "
    f"data: yfinance + Kalshi public API  ·  "
    f"cache TTL: 5 min"
)
