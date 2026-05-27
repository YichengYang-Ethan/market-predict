"""Streamlit entry: visual dashboard for a single ticker view.

Layout v2: 6 rows of panels + 1 tabs row, designed for ~1440×900 screens with
minimal scrolling. Same-dimension multi-source data is placed side-by-side.

Run locally:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

from pathlib import Path

import requests
import streamlit as st

from market_predict.cli import build_view
from market_predict.snapshot import load_snapshot, load_snapshot_from_text
from market_predict.tickers import TICKER_MAP, get_config
from market_predict.ui import charts


st.set_page_config(page_title="market-predict", page_icon="📊", layout="wide")

# Snapshot pipeline:
# - A GitHub Actions cron writes data/snapshot_<SYM>.json to the `snapshots`
#   branch (deliberately not main, to avoid Streamlit Cloud redeploys every
#   15 min). Streamlit pulls those files over HTTP from raw.githubusercontent.
# - Locally, `data/snapshot_<SYM>.json` is used as a dev override.
# - If both miss, we fall back to a slow live `build_view`.
SNAPSHOT_URLS = [
    # statically.io is a global CDN proxying GitHub — measured 1-4s where
    # raw.githubusercontent.com runs 5-30s. Try it first.
    "https://cdn.statically.io/gh/YichengYang-Ethan/market-predict/snapshots/data/snapshot_{symbol}.json",
    # raw.githubusercontent.com is the official fallback if statically is down
    "https://raw.githubusercontent.com/YichengYang-Ethan/market-predict/snapshots/data/snapshot_{symbol}.json",
]
SNAPSHOT_DIR_LOCAL = Path(__file__).resolve().parent.parent.parent / "data"


@st.cache_data(ttl=900, show_spinner=False)
def load_view(symbol: str):
    # 1. Local dev override
    local = SNAPSHOT_DIR_LOCAL / f"snapshot_{symbol}.json"
    if local.exists():
        snap = load_snapshot(local)
        if snap is not None:
            snap._source = "snapshot (local file)"
            return snap

    # 2. Remote snapshot from one of the CDNs (in order, first hit wins)
    for url_tpl in SNAPSHOT_URLS:
        try:
            r = requests.get(url_tpl.format(symbol=symbol), timeout=8)
            if r.ok:
                snap = load_snapshot_from_text(r.text)
                if snap is not None:
                    snap._source = "snapshot (CDN)"
                    return snap
        except requests.RequestException:
            continue

    # 3. Last resort: live fetch (~13s on a clean IP, can be 30s+ if throttled)
    view = build_view(symbol)
    view._source = "live fetch"
    return view


def _short_fed_outcome(question: str) -> str:
    """Compress 'Will the Fed decrease interest rates by 25 bps after the June...' → 'Cut 25bp'."""
    q = question.lower()
    if "no change" in q or "maintain" in q:
        return "Hold"
    if "decrease" in q or "cut" in q:
        if "50" in q:
            return "Cut ≥50bp"
        if "25" in q:
            return "Cut 25bp"
        return "Cut"
    if "increase" in q or "hike" in q:
        if "50" in q:
            return "Hike ≥50bp"
        if "25" in q:
            return "Hike 25bp"
        return "Hike"
    return question[:30]


def _short_rate_cuts_outcome(question: str) -> str:
    """'Will N Fed rate cuts happen in 2026?' → 'N cuts'."""
    import re
    m = re.search(r"(?:Will\s+)?(\w+)\s+Fed rate cuts?", question, re.IGNORECASE)
    if m:
        n = m.group(1)
        if n.lower() in ("no", "zero", "0"):
            return "0 cuts"
        return f"{n} cut{'s' if n != '1' else ''}"
    return question[:30]


# ────────────────────── Header (title + controls) ─────────────────────


st.markdown(
    "<h1 style='margin-bottom:0;'>market-predict</h1>"
    "<p style='color:#7f8c8d;font-size:0.9em;margin-top:0;'>"
    "SPY/QQQ trader context · spot · options walls · Kalshi & Polymarket predictions · Fed. "
    "All sources free and public.</p>",
    unsafe_allow_html=True,
)

ctrl_l, ctrl_r = st.columns([5, 1])
with ctrl_l:
    symbol = st.selectbox(
        "Ticker", list(TICKER_MAP.keys()), index=0, label_visibility="collapsed"
    )
with ctrl_r:
    if st.button("Refresh", use_container_width=True):
        load_view.clear()
        st.rerun()

with st.spinner(f"Fetching {symbol} data..."):
    try:
        view = load_view(symbol)
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        st.stop()

cfg = get_config(symbol)

# Warn (don't stop) when yfinance is rate-limited — Kalshi/Polymarket panels
# can still render. Streamlit Cloud's shared IP pool hits Yahoo throttles often.
if not view.spot or not view.underlying_value:
    st.warning(
        "Yahoo Finance is rate-limiting this host (common on Streamlit Cloud's "
        "shared IPs). Spot/options/VIX panels will show 'n/a' — Kalshi and "
        "Polymarket panels below are unaffected. Try Refresh in a few minutes."
    )


# ─────────────────────────── HEADER METRICS ──────────────────────────


m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric(view.symbol, f"${view.spot:.2f}" if view.spot else "n/a")
m2.metric(view.underlying_name, f"{view.underlying_value:,.2f}" if view.underlying_value else "n/a")
if view.futures is not None:
    m3.metric(
        f"{view.futures.name} fut",
        f"{view.futures.last:,.2f}",
        f"{view.futures.change_pct:+.2f}% o/n",
    )
else:
    m3.metric("Futures", "n/a")
if view.vix is not None:
    vix_delta = view.vix.current - view.vix.mean_30d
    m4.metric("VIX", f"{view.vix.current:.2f}", f"{vix_delta:+.2f} vs 1m avg", delta_color="inverse")
else:
    m4.metric("VIX", "n/a")
# Defensive: an old cached snapshot may have wall != None but with all-zero
# OI from the pre-fix compute_wall logic. Treat that as "no wall available"
# so we don't display misleading $0-OI numbers.
_wall = view.options_wall
_wall_ok = _wall is not None and (_wall.call_wall_oi > 0 or _wall.put_wall_oi > 0)
if _wall_ok:
    m5.metric("ATM IV", f"{_wall.atm_iv * 100:.1f}%")
    pc = _wall.total_put_oi / max(_wall.total_call_oi, 1)
    m6.metric("P/C OI", f"{pc:.2f}")
else:
    m5.metric("ATM IV", "n/a")
    m6.metric("P/C OI", "n/a")

st.markdown("")  # subtle spacer instead of divider


# ───────────────────── ROW 1: K-line + VIX mini ─────────────────────


row1_l, row1_r = st.columns([2.5, 1])
with row1_l:
    st.plotly_chart(charts.price_history(view), use_container_width=True)
with row1_r:
    st.plotly_chart(charts.vix_mini(view), use_container_width=True)


# ───────────────────── ROW 2: Options walls + key levels ────────────


st.markdown("##### Options walls")
if _wall_ok:
    row2_l, row2_r = st.columns([2.5, 1])
    with row2_l:
        st.plotly_chart(charts.options_wall(view), use_container_width=True)
    with row2_r:
        w = _wall
        st.metric("Call wall", f"${w.call_wall_strike:.0f}", f"{w.call_wall_oi:,} OI")
        st.metric("Put wall", f"${w.put_wall_strike:.0f}", f"{w.put_wall_oi:,} OI")
        st.metric("Max pain", f"${w.max_pain:.0f}")
        st.metric(
            "Gamma flip",
            f"${w.gamma_flip:.0f}" if w.gamma_flip is not None else "n/a",
        )
else:
    st.info(
        "Options walls unavailable — Yahoo Finance stopped publishing real near-spot OI "
        "for large ETFs (SPY/QQQ) around 2024. All other panels use live data."
    )

st.markdown("")


# ───────────── ROW 3: Today's direction (Kalshi + Poly daily) ────────


st.markdown("##### Today's direction · dual-source")
row3_l, row3_r = st.columns([2.5, 1])

with row3_l:
    # Dual-source close brackets chart (Kalshi $25 SPX brackets + Poly $5 SPY cumulative)
    if view.kalshi_daily or view.polymarket_daily_close_brackets:
        st.plotly_chart(
            charts.daily_brackets_dual(
                view.kalshi_daily,
                view.polymarket_daily_close_brackets,
                view.spot,
                view.underlying_value,
                view.underlying_name,
                cfg.get("spx_to_spy_ratio", 10.0),
            ),
            use_container_width=True,
        )
    else:
        st.info("No daily brackets data (Kalshi or Polymarket).")

with row3_r:
    # Up/Down binary metrics (close + premarket)
    if view.polymarket_daily_updown is not None:
        pd_ud = view.polymarket_daily_updown
        st.metric(
            f"P(close UP {pd_ud.end_date})",
            f"{pd_ud.p_up * 100:.1f}%",
            f"{(pd_ud.p_up - 0.5) * 100:+.1f} pp",
        )
        st.caption(f"vol24 ${pd_ud.volume_24h:,.0f}")
    else:
        st.metric("P(close UP)", "n/a")

    if view.polymarket_premarket_updown is not None:
        pd_pre = view.polymarket_premarket_updown
        st.metric(
            f"P(open UP {pd_pre.end_date})",
            f"{pd_pre.p_up * 100:.1f}%",
            f"{(pd_pre.p_up - 0.5) * 100:+.1f} pp",
        )
        st.caption(f"vol24 ${pd_pre.volume_24h:,.0f}")
    else:
        st.metric("P(open UP)", "n/a")
        st.caption("Polymarket premarket event not active right now.")

st.markdown("")


# ───────────── ROW 4: Fed/rates (3 panels) ────────────


st.markdown("##### Fed & rates")
row4_a, row4_b, row4_c = st.columns([2, 1, 1])

with row4_a:
    st.plotly_chart(charts.fed_path(view), use_container_width=True)

with row4_b:
    st.plotly_chart(
        charts.kalshi_event_outcomes_bar(
            view.kalshi_rate_cut_count,
            title="Kalshi · 2026 rate cuts count",
        ),
        use_container_width=True,
    )

with row4_c:
    if view.polymarket_fed_decision is not None:
        from market_predict.models import FedMeeting, FedOutcome
        wrapped = FedMeeting(
            event_ticker=view.polymarket_fed_decision.slug,
            close_time=view.polymarket_fed_decision.end_date,
            outcomes=[
                FedOutcome(
                    ticker="",
                    title=_short_fed_outcome(o.question),
                    yes_mid=o.yes_price,
                    open_interest=o.open_interest,
                    volume_24h=o.volume_24h,
                )
                for o in view.polymarket_fed_decision.markets
            ],
        )
        st.plotly_chart(
            charts.kalshi_event_outcomes_bar(
                wrapped,
                title="Polymarket · next FOMC",
                color=charts.COLORS["polymarket"],
            ),
            use_container_width=True,
        )
    else:
        st.info("Polymarket Fed Decision event not found.")

st.markdown("")


# ─────────────────────────── TABS row ───────────────────────────────
# Streamlit `st.tabs` is eager — *all* tab content renders on every
# rerun, even tabs you don't click. With 6 extra Plotly charts that
# adds ~2-3s on slow shared-CPU instances. Gate them behind a button
# so the first load only paints the essentials (5 charts in rows 1-4).

if st.session_state.get("show_extras", False):
    tab_monthly, tab_yearly, tab_macro, tab_mag7, tab_rates_2026 = st.tabs(
        ["Monthly", "Yearly", "Macro / Recession", "Mag 7", "2026 Cuts"]
    )
else:
    if st.button("📊  Show extras — Monthly, Yearly, Recession, Mag 7, 2026 Cuts", type="secondary"):
        st.session_state.show_extras = True
        st.rerun()
    st.caption("Hidden by default to keep first load under ~10 s. Click to reveal.")
    st.stop()

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
            f"**One-touch contracts** · Yes resolves if the underlying touches "
            f"the strike at any point before {view.polymarket_monthly.end_date}. "
            f"Not mutually exclusive — each strike is its own bet. "
            f"**Gap around spot is intentional**: Polymarket only lists OTM strikes "
            f"(HIGH > spot, LOW < spot) since ATM contracts would already be resolved. "
            f"Source: Polymarket, event vol24 ≈ ${view.polymarket_monthly.volume_24h:,.0f}. "
            f"(Kalshi does not currently list monthly range contracts.)"
        )
    else:
        st.info("No active monthly Polymarket one-touch.")

with tab_yearly:
    yc_l, yc_r = st.columns([2, 1])
    with yc_l:
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
    with yc_r:
        st.markdown(f"**{view.underlying_name} year MAX one-touch** (Kalshi)")
        if view.kalshi_year_max:
            # Already cumulative; show first 5 sorted by strike
            top = sorted(view.kalshi_year_max, key=lambda b: b.strike_low or 0)[:6]
            for b in top:
                if b.strike_low:
                    st.write(
                        f"P(year max ≥ {b.strike_low:,.0f}) = **{b.yes_mid*100:.1f}%**  "
                        f"<span style='color:#7f8c8d;font-size:0.85em'>OI {b.open_interest:,.0f} ctrs</span>",
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("No data")

        st.markdown("---")
        st.markdown(f"**{view.underlying_name} year MIN one-touch** (Kalshi)")
        if view.kalshi_year_min:
            top = sorted(view.kalshi_year_min, key=lambda b: -(b.strike_high or 0))[:6]
            for b in top:
                if b.strike_high:
                    st.write(
                        f"P(year min ≤ {b.strike_high:,.0f}) = **{b.yes_mid*100:.1f}%**  "
                        f"<span style='color:#7f8c8d;font-size:0.85em'>OI {b.open_interest:,.0f} ctrs</span>",
                        unsafe_allow_html=True,
                    )
        else:
            st.caption("No data")

with tab_macro:
    mc_l, mc_r = st.columns([1, 1])
    with mc_l:
        st.plotly_chart(
            charts.recession_gauge(view.kalshi_recession),
            use_container_width=True,
        )
        if view.kalshi_recession:
            for b in view.kalshi_recession:
                st.caption(
                    f"**{b.event_ticker}** — *{b.title}*  "
                    f"P = {b.yes_mid * 100:.1f}%  ·  OI {b.open_interest:,.0f} ctrs"
                )
    with mc_r:
        st.markdown("### Notes")
        st.markdown(
            "- **NBER recession** = National Bureau of Economic Research formal recession call. "
            "Lagging indicator, but contract resolves YES if NBER declares recession start in the period.\n"
            "- Historical base rate of recession in any given year ≈ 16–17%.\n"
            "- Reference threshold (blue line) on the gauge = 16.5%.\n"
            f"- Source: Kalshi `KXRECSSNBER` event, total OI ≈ {sum(b.open_interest for b in view.kalshi_recession):,.0f} contracts."
        )

with tab_mag7:
    st.plotly_chart(
        charts.mag7_ranking_bar(view.polymarket_largest_company),
        use_container_width=True,
    )
    if view.polymarket_largest_company:
        st.caption(
            f"**{view.polymarket_largest_company.title}** · "
            f"event vol24 ≈ ${view.polymarket_largest_company.volume_24h:,.0f}. "
            f"Source: Polymarket. NVDA/AAPL/MSFT/etc. dominate S&P 500 weight, so this ranks "
            f"the AI-theme winner."
        )

with tab_rates_2026:
    if view.polymarket_rate_cuts_2026:
        from market_predict.models import FedMeeting, FedOutcome
        wrapped = FedMeeting(
            event_ticker=view.polymarket_rate_cuts_2026.slug,
            close_time=view.polymarket_rate_cuts_2026.end_date,
            outcomes=[
                FedOutcome(
                    ticker="",
                    title=_short_rate_cuts_outcome(o.question),
                    yes_mid=o.yes_price,
                    open_interest=o.open_interest,
                    volume_24h=o.volume_24h,
                )
                for o in view.polymarket_rate_cuts_2026.markets
            ],
        )
        st.plotly_chart(
            charts.kalshi_event_outcomes_bar(
                wrapped,
                title="Polymarket · How many Fed rate cuts in 2026?",
                color=charts.COLORS["polymarket"],
            ),
            use_container_width=True,
        )
        st.caption(
            f"Compare to Kalshi `KXRATECUTCOUNT` in the Fed row above — same question, "
            f"two platforms. Event vol24 ≈ ${view.polymarket_rate_cuts_2026.volume_24h:,.0f}."
        )
    else:
        st.info("Polymarket 'rate cuts in 2026' event not found.")

st.markdown("---")
_ts = view.timestamp
_ts_str = _ts.strftime("%Y-%m-%d %H:%M") if hasattr(_ts, "strftime") else str(_ts)[:16]
_source = getattr(view, "_source", "live fetch")
_source_label = {
    "snapshot (CDN)": "📦 snapshot via CDN (GitHub Actions, refreshed every 15 min)",
    "snapshot (local file)": "📦 snapshot (local dev file)",
    "live fetch": "🛰️ live fetch (Kalshi + Polymarket + yfinance)",
}.get(_source, _source)
st.caption(
    f"Data · {_ts_str}  ·  {_source_label}  ·  cache TTL · 15 min"
)
