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
from market_predict.sources.yfin import get_cross_asset
from market_predict.tickers import TICKER_MAP, get_config
from market_predict.transforms.setup import build_setup
from market_predict.ui import charts


@st.cache_data(ttl=900, show_spinner=False)
def load_cross_asset():
    """Small macro cross-section (5 ETFs), cached so reruns don't refetch."""
    return get_cross_asset()


st.set_page_config(page_title="market-predict", page_icon="📊", layout="wide")

# ── Visual chrome. Editorial style ported from yichengyang-ethan.github.io:
#    warm cream canvas, deep-red accent, Source Serif 4 headlines, Inter UI
#    labels, JetBrains-Mono numbers, white cards with warm borders. Pure CSS. ──
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

      :root {
        --bg:#faf9f7; --text:#1a1a1a; --text2:#555; --accent:#c4170c;
        --accent-light:#fef2f1; --border:#e5e3df; --card:#fff; --code:#f5f4f0;
        --shadow:0 1px 3px rgba(26,26,26,.05); --shadow-lg:0 6px 22px rgba(26,26,26,.08);
      }

      /* base */
      html, body, [class*="css"], .stApp, .stMarkdown, p, li, span, label,
        [data-testid="stWidgetLabel"] { font-family:'Inter', sans-serif; }
      .stApp { background:var(--bg); }
      .block-container { padding-top:1.1rem !important; padding-bottom:2.5rem !important; max-width:1280px; }
      [data-testid="stToolbar"], #MainMenu, footer { display:none; }
      header[data-testid="stHeader"] { background:transparent; height:0; }

      /* ── editorial header (mirrors site <header>) ── */
      .mp-head { border-bottom:1px solid var(--border); padding:4px 0 22px; margin:0 0 24px; }
      .mp-eyebrow { font-family:'Inter',sans-serif; font-size:12px; font-weight:600; letter-spacing:1.5px;
        text-transform:uppercase; color:var(--accent); margin-bottom:12px; }
      .mp-head h1 { font-family:'Source Serif 4',Georgia,serif; font-size:40px; line-height:1.12;
        font-weight:700; letter-spacing:-.5px; color:var(--text); margin:0 0 12px; }
      .mp-sub { font-family:'Source Serif 4',Georgia,serif; font-size:19px; color:var(--text2);
        line-height:1.5; margin:0; }
      .mp-sub .mp-mono { font-family:'JetBrains Mono',monospace; font-size:13px; color:var(--accent); }

      /* ── section headings: dark label, cream rule + short accent tick (Krish) ── */
      h5 { font-family:'Inter',sans-serif !important; font-size:12.5px !important; font-weight:700 !important;
        letter-spacing:1.6px; text-transform:uppercase; color:var(--text) !important;
        margin:32px 0 16px !important; padding:0 0 9px 0 !important; position:relative;
        border-bottom:1px solid var(--border); }
      h5::after { content:''; position:absolute; left:0; bottom:-1px; width:46px; height:2px; background:var(--accent); }

      /* ── metric tiles → institutional stat-cards (cream header strip + value body) ── */
      [data-testid="stMetric"] { background:var(--card); border:1px solid var(--border); border-radius:8px;
        padding:0 0 6px 0; overflow:hidden; box-shadow:var(--shadow);
        transition:transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
      [data-testid="stMetric"]:hover { transform:translateY(-2px); box-shadow:var(--shadow-lg); border-color:var(--accent); }
      [data-testid="stMetricLabel"] { background:var(--code); border-bottom:1px solid var(--border);
        padding:6px 14px 5px !important; margin:0 0 4px 0 !important; width:100%; }
      [data-testid="stMetricLabel"] p { font-family:'Inter',sans-serif !important; font-weight:600 !important;
        font-size:.67rem !important; text-transform:uppercase; letter-spacing:.09em; color:var(--text2) !important; }
      [data-testid="stMetricValue"] { font-family:'JetBrains Mono',monospace !important; color:var(--text) !important;
        font-weight:700 !important; font-size:1.5rem !important; padding:6px 14px 0 !important; }
      [data-testid="stMetricDelta"] { font-family:'JetBrains Mono',monospace !important; font-size:.76rem !important;
        padding:1px 14px 0 !important; }

      /* ── plotly charts → cards ── */
      [data-testid="stPlotlyChart"] { background:var(--card); border:1px solid var(--border); border-radius:10px;
        padding:10px 12px 4px; box-shadow:var(--shadow); transition:box-shadow .2s ease, border-color .2s ease; }
      [data-testid="stPlotlyChart"]:hover { box-shadow:var(--shadow-lg); border-color:#dcd8cf; }
      /* hide Plotly's hover toolbar (camera/zoom/pan) for a cleaner, static look */
      .js-plotly-plot .modebar { display:none !important; }

      /* ── synthesis callout + inline breakdown (no click-to-expand) ── */
      .mp-callout { background:var(--accent-light); border:1px solid #f3d9d6; border-left:4px solid var(--accent);
        padding:15px 22px; margin:6px 0 4px; border-radius:0 8px 8px 0; }
      .mp-callout .t { font-family:'Inter',sans-serif; font-weight:700; color:var(--accent); font-size:.74rem;
        text-transform:uppercase; letter-spacing:.09em; }
      .mp-callout .v { font-family:'Source Serif 4',Georgia,serif; color:var(--text); font-size:1.12rem;
        line-height:1.4; margin-top:4px; }
      .mp-breakdown { margin:2px 0 10px 2px; }
      .mp-breakdown p { font-family:'Inter',sans-serif; color:var(--text2); font-size:.84rem; line-height:1.5; margin:0; }
      .mp-breakdown li { font-family:'Inter',sans-serif; color:var(--text2); font-size:.84rem; line-height:1.6; }
      .mp-breakdown strong, .mp-breakdown b { color:var(--text); font-weight:600; }

      /* ── controls strip ── */
      .st-key-mpctrl { background:var(--card); border:1px solid var(--border); border-radius:8px;
        padding:8px 14px 4px !important; box-shadow:var(--shadow); margin-bottom:8px; }
      [data-testid="stSelectbox"] div[data-baseweb="select"] > div { border-color:var(--border) !important;
        border-radius:6px; font-family:'Inter',sans-serif; }
      [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover { border-color:var(--accent) !important; }

      /* ── captions / buttons / tabs / alerts / footer ── */
      [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
        font-family:'Inter',sans-serif; color:var(--text2); }
      [data-testid="stExpander"] { border:1px solid var(--border) !important; border-radius:8px; background:var(--card); }
      .stButton button { font-family:'Inter',sans-serif; border-radius:6px; font-weight:600;
        border:1px solid var(--border); color:var(--text); background:var(--card); letter-spacing:.02em; }
      .stButton button:hover { border-color:var(--accent); color:var(--accent); background:var(--accent-light); }
      .stTabs [data-baseweb="tab-list"] { gap:2px; border-bottom:2px solid var(--border); }
      .stTabs [data-baseweb="tab"] { font-family:'Inter',sans-serif; font-size:.78rem; font-weight:600;
        text-transform:uppercase; letter-spacing:.06em; color:var(--text2) !important; padding:8px 16px; }
      .stTabs [data-baseweb="tab"]:hover { color:var(--text) !important; background:var(--code); }
      .stTabs [aria-selected="true"] { color:var(--accent) !important; }
      .stTabs [data-baseweb="tab-highlight"] { background:var(--accent) !important; height:3px; }
      [data-testid="stAlert"] { border-radius:8px; font-family:'Inter',sans-serif; }
      hr { border-color:var(--border); }
    </style>
    """,
    unsafe_allow_html=True,
)

# When embedded in yichengyang-ethan.github.io (iframe ?site=1), the host page
# already renders a "market-predict" header, so suppress this app's own header
# and tighten the top padding for a seamless, single-page feel.
IS_EMBED = st.query_params.get("site") == "1"
if IS_EMBED:
    # Trim top padding AND defeat Streamlit's inner scroll container so the app
    # lays out at its full natural height — then the host iframe can grow to fit
    # (no inner scrollbar) and document.body.scrollHeight reads true.
    st.markdown(
        "<style>"
        ".block-container{padding-top:.4rem !important;}"
        "[data-testid='stAppViewContainer'],section[data-testid='stMain'],"
        "[data-testid='stAppViewContainer']>.main"
        "{height:auto !important;max-height:none !important;overflow:visible !important;}"
        "</style>",
        unsafe_allow_html=True,
    )

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


if not IS_EMBED:
    st.markdown(
        "<div class='mp-head'>"
        "<div class='mp-eyebrow'>Live Market Dashboard</div>"
        "<h1>market-predict</h1>"
        "<p class='mp-sub'>SPY / QQQ trader context — spot, options walls, dealer gamma, "
        "Kalshi &amp; Polymarket predictions, and the Fed path. "
        "<span class='mp-mono'>free data · refreshed every 15 min</span></p>"
        "</div>",
        unsafe_allow_html=True,
    )

with st.container(key="mpctrl"):
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


# ───────────────────── Today's setup (synthesis) ────────────────────
# One read of the page: gamma regime + walls + positioning + vol + implied
# direction, from fields already on `view` (no extra fetch). Descriptive, not
# advice. See transforms/setup.py.


_setup = build_setup(view)
if _setup is not None:
    st.markdown(
        "<div class='mp-callout'>"
        f"<div class='t'>Today's setup — {_setup.tag}</div>"
        f"<div class='v'>{_setup.verdict}</div></div>",
        unsafe_allow_html=True,
    )
    # Breakdown rendered inline (no click-to-expand) — the gamma / walls /
    # positioning / vol / implied-direction reads behind the verdict above.
    if _setup.lines:
        import re as _re
        _items = "".join(
            "<p>• " + _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _ln) + "</p>"
            for _ln in _setup.lines
        )
        st.markdown(f"<div class='mp-breakdown'>{_items}</div>", unsafe_allow_html=True)


# ───────────────────── Cross-asset risk strip ───────────────────────
# Macro context the index page otherwise lacks (rates / credit / USD / gold /
# oil). Live + cached; degrades to a caption when yfinance is throttled.


st.markdown("##### Cross-asset")
_ca = load_cross_asset()
if _ca:
    _cols = st.columns(len(_ca))
    for _col, _a in zip(_cols, _ca):
        _col.metric(_a.name, f"{_a.last:,.2f}", f"{_a.chg_1d:+.2f}% 1d")
        _col.caption(f"5d {_a.chg_5d:+.2f}%")
else:
    st.caption("Cross-asset quotes unavailable (yfinance throttled). Try Refresh in a minute.")

st.markdown("")


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
        "Options walls unavailable — the CBOE delayed-quote feed returned no near-spot "
        "open interest for this snapshot. All other panels use live data."
    )

st.markdown("")


# ─────────────── ROW 2b: Dealer gamma (GEX) profile ─────────────────


st.markdown("##### Dealer gamma profile (GEX)")
if _wall_ok:
    gex_l, gex_r = st.columns([2.5, 1])
    with gex_l:
        st.plotly_chart(charts.gex_profile(view), use_container_width=True)
    with gex_r:
        st.caption(
            "Net dealer gamma vs price (dealers long calls / short puts). "
            "**Above** the γ-flip → positive gamma: dealer hedging leans **against** "
            "moves (vol-dampening, mean-reverting). **Below** → negative gamma: hedging "
            "**chases** moves (vol-amplifying, breakout-prone). Same data as the walls, "
            "recomputed from the snapshot chain. Magnitude is indicative."
        )
else:
    st.info("GEX unavailable — no near-spot open interest in this snapshot.")

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


# ─────────────────────────── More markets (tabs) ────────────────────
# All tabs render inline — no click-to-reveal gate. st.tabs is eager, so
# every panel paints on load; on a warm snapshot that is a couple extra
# seconds, traded for everything being reachable without a click.

st.markdown("##### More markets")
tab_monthly, tab_yearly, tab_macro, tab_mag7, tab_rates_2026 = st.tabs(
    ["Monthly", "Yearly", "Macro / Recession", "Mag 7", "2026 Cuts"]
)

with tab_monthly:
    if view.polymarket_monthly is not None and view.polymarket_monthly.brackets:
        st.warning(
            "**Read this before reading the chart** — this is **NOT a probability "
            "distribution**. Each point is a path-dependent barrier bet: "
            "*P(SPX touches this strike at any point before "
            f"{view.polymarket_monthly.end_date})*. Probabilities do NOT sum to 100% "
            "because a single path can hit multiple strikes (e.g. SPX rallies to 7700 "
            "then drops to 7000 → both the HIGH 7600 and LOW 7100 contracts pay YES).",
            icon="ℹ️",
        )
        st.plotly_chart(
            charts.polymarket_one_touch(
                view.polymarket_monthly,
                view.underlying_value,
                view.underlying_name,
            ),
            use_container_width=True,
        )
        st.caption(
            f"**Gap around spot is intentional** — Polymarket only lists OTM strikes "
            f"(HIGH > spot, LOW < spot). ATM one-touch contracts (\"will SPX touch "
            f"X when spot is already past X\") would resolve YES trivially, so the "
            f"exchange doesn't list them. "
            f"Source: Polymarket, event vol24 ≈ ${view.polymarket_monthly.volume_24h:,.0f}. "
            f"For a real distribution (probabilities sum to 100%), see the **Yearly** "
            f"tab — Kalshi does not currently list a monthly range product."
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


# When embedded (?site=1), report this app's full content height up to the host
# page so the iframe can grow to fit — no inner scrollbar, the whole thing scrolls
# as one page. The component runs same-origin with the Streamlit doc (so it can
# read its height) and postMessages to window.top (the github.io page).
if IS_EMBED:
    import streamlit.components.v1 as _components
    _components.html(
        """
        <script>
        (function () {
          function measure(d) {
            // Streamlit's content lives in the block container (the body itself
            // stays viewport-sized), so measure that — plus a few fallbacks.
            var sels = ['[data-testid="stMainBlockContainer"]', '.block-container',
                        '[data-testid="stAppViewContainer"]', 'section[data-testid="stMain"]'];
            var h = 0, el;
            for (var i = 0; i < sels.length; i++) {
              el = d.querySelector(sels[i]);
              if (el) h = Math.max(h, el.scrollHeight, el.offsetHeight,
                                   Math.ceil(el.getBoundingClientRect().height));
            }
            return Math.max(h, d.body.scrollHeight, d.documentElement.scrollHeight);
          }
          function send() {
            try { window.top.postMessage({ mpHeight: measure(window.parent.document) }, "*"); }
            catch (e) {}
          }
          send();
          setInterval(send, 600);
          try { new ResizeObserver(send).observe(window.parent.document.body); } catch (e) {}
          window.addEventListener("load", send);
        })();
        </script>
        """,
        height=0,
    )
