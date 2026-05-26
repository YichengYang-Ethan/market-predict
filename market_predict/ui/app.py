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

# Header metrics — two rows
# Row 1: ticker / underlying / futures / VIX
r1_a, r1_b, r1_c, r1_d = st.columns(4)
r1_a.metric(view.symbol, f"${view.spot:.2f}")
r1_b.metric(view.underlying_name, f"{view.underlying_value:,.2f}")

if view.futures is not None:
    r1_c.metric(
        f"{view.futures.name} futures",
        f"{view.futures.last:,.2f}",
        f"{view.futures.change_pct:+.2f}% overnight",
    )
else:
    r1_c.metric(f"futures", "n/a")

if view.vix is not None:
    vix_delta = view.vix.current - view.vix.mean_30d
    r1_d.metric(
        "VIX",
        f"{view.vix.current:.2f}",
        f"{vix_delta:+.2f} vs 30d avg",
        delta_color="inverse",  # higher VIX = bad
    )
else:
    r1_d.metric("VIX", "n/a")

# Row 2: options-derived (ATM IV, P/C ratio) — only if we have options
if view.options_wall:
    r2_a, r2_b, _, _ = st.columns(4)
    r2_a.metric("ATM IV", f"{view.options_wall.atm_iv * 100:.1f}%")
    pc = view.options_wall.total_put_oi / max(view.options_wall.total_call_oi, 1)
    r2_b.metric("Put/Call OI", f"{pc:.2f}")

st.divider()

# Price history + VIX mini side-by-side
ph_l, ph_r = st.columns([2.5, 1])
with ph_l:
    st.plotly_chart(charts.price_history(view), use_container_width=True)
with ph_r:
    st.plotly_chart(charts.vix_mini(view), use_container_width=True)
    if view.futures is not None:
        st.caption(
            f"📌 **{view.futures.name} {view.futures.last:,.2f}** "
            f"({view.futures.change_pct:+.2f}% vs prev close ${view.futures.previous_close:,.2f}). "
            f"Overnight futures lead the cash open."
        )

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
    tab_daily, tab_monthly, tab_yearly = st.tabs(["Daily", "Monthly", "Yearly"])

    with tab_daily:
        # Polymarket binary up/down at top — single most-watched daily signal
        if view.polymarket_daily_updown is not None:
            pd_ud = view.polymarket_daily_updown
            up_col, down_col, vol_col = st.columns([1, 1, 1])
            # Direction-tinted: green if up>down, red otherwise (delta carries arrow)
            up_delta = f"{(pd_ud.p_up - 0.5) * 100:+.1f} pp vs coin-flip"
            down_delta = f"{(pd_ud.p_down - 0.5) * 100:+.1f} pp vs coin-flip"
            up_col.metric(
                f"Poly P({view.underlying_name} UP {pd_ud.end_date})",
                f"{pd_ud.p_up * 100:.1f}%",
                up_delta,
            )
            down_col.metric(
                f"Poly P({view.underlying_name} DOWN {pd_ud.end_date})",
                f"{pd_ud.p_down * 100:.1f}%",
                down_delta,
                delta_color="inverse",
            )
            vol_col.metric("Poly vol24", f"${pd_ud.volume_24h:,.0f}")
            st.caption(
                f"📌 *{pd_ud.title}* — single binary, resolves on close. "
                f"Source: Polymarket."
            )
            st.divider()

        # Kalshi distribution below
        if view.kalshi_daily:
            close_time = view.kalshi_daily[0].close_time
            st.plotly_chart(
                charts.kalshi_distribution(
                    view.kalshi_daily,
                    view.underlying_value,
                    view.underlying_name,
                    f"Kalshi {view.underlying_name} — resolves {close_time}",
                ),
                use_container_width=True,
            )
            st.caption(
                "⚠️ Daily Kalshi brackets have low OI (~$0.3k–3k vs yearly $1.8M–2.6M). "
                "Treat as directional signal only."
            )
        elif view.polymarket_daily_updown is None:
            st.info("No active daily contracts (Kalshi or Polymarket) for this underlying.")

    with tab_monthly:
        if view.polymarket_monthly is not None and view.polymarket_monthly.brackets:
            st.plotly_chart(
                charts.polymarket_one_touch(
                    view.polymarket_monthly,
                    view.underlying_value,
                    view.underlying_name,
                ),
                use_container_width=True,
            )
            st.caption(
                f"📌 **One-touch contracts**: Yes resolves if the underlying touches "
                f"the strike at any point before {view.polymarket_monthly.end_date}. "
                f"Not mutually exclusive — each strike is its own bet. "
                f"Source: Polymarket, event vol24 ≈ ${view.polymarket_monthly.volume_24h:,.0f}. "
                f"(Kalshi does not currently list monthly range contracts.)"
            )
        else:
            st.info(
                "**No active monthly contracts** for this underlying. "
                "Kalshi has no monthly range series active; "
                f"Polymarket has no one-touch event matching {view.underlying_name}. "
                "This tab will populate automatically if either platform lists one."
            )

    with tab_yearly:
        if view.kalshi_yearly:
            close_time = view.kalshi_yearly[0].close_time
            st.plotly_chart(
                charts.kalshi_distribution(
                    view.kalshi_yearly,
                    view.underlying_value,
                    view.underlying_name,
                    f"Kalshi {view.underlying_name} — resolves {close_time}",
                ),
                use_container_width=True,
            )
        else:
            st.info("No active yearly Kalshi brackets.")

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
