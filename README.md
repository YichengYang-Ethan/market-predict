# market-predict

Single-page market dashboard for **SPY/QQQ traders**. Pulls 18 free public data feeds — spot, options walls, Kalshi prediction-market distributions, Polymarket binary bets, Fed path — into one Streamlit page with zero auth keys, zero servers, and zero ongoing cost.

> **Deploy your own free copy** in 5 minutes via [share.streamlit.io](https://share.streamlit.io): pick this repo, branch `main`, file `streamlit_app.py`. The URL you choose (e.g. `your-name.streamlit.app`) is shareable — anyone with the link can view, no login.

---

## What it shows

| Row | Panels | Sources |
|---|---|---|
| **Header** | spot · underlying · futures (overnight) · VIX · ATM IV · P/C OI | yfinance |
| **Row 1** | 3-month K-line + volume · VIX 1m mini | yfinance |
| **Row 2** | Options walls (call/put OI, max pain, γ flip) · key levels | yfinance options chain |
| **Row 3** | Daily close brackets — **Kalshi + Polymarket overlaid** · today's UP/DOWN binary | Kalshi `KXINX` · Polymarket `closes above` |
| **Row 4** | FOMC stacked path · Kalshi rate-cuts count · Polymarket next-FOMC outcomes | Kalshi `KXFEDDECISION`, `KXRATECUTCOUNT` · Polymarket |
| **Tabs** | Monthly one-touch · Yearly distribution + year-max/min · Recession gauge · Mag 7 ranking · 2026 cuts count | Polymarket · Kalshi `KXINXY`, `KXINXMAXY/MINY`, `KXRECSSNBER` · Polymarket `big-tech` |

Every Kalshi/Polymarket panel cites event ticker + close date + 24h volume for traceability.

## Quick start

```bash
git clone https://github.com/YichengYang-Ethan/market-predict
cd market-predict
pip install -e .[ui]
streamlit run streamlit_app.py
```

Open `http://localhost:8501`. Switch ticker (SPY/QQQ) in the dropdown; hit **Refresh** to bust the 5-minute cache.

CLI-only text snapshot (no Streamlit):

```bash
pip install -e .
python -m market_predict SPY
```

### Deploy to Streamlit Community Cloud

1. Fork this repo on GitHub
2. [share.streamlit.io](https://share.streamlit.io) → New app → connect repo, branch `main`, file `streamlit_app.py`
3. Deploy. Auto-redeploys on every push to `main`. No secrets to configure.

## Data sources (all free, all public)

### yfinance
- Spot price, 3-month OHLCV history (auto-adjust off)
- Options chain — call/put OI, IV, expirations (15-min delayed OPRA)
- VIX (`^VIX`) — 1-month history + spot
- E-mini futures (`ES=F` / `NQ=F`) — overnight change vs previous close

### Kalshi public API (no auth)
Endpoint: `api.elections.kalshi.com/trade-api/v2/markets?series_ticker=X`

| Series | Used for |
|---|---|
| `KXINXY` / `KXNASDAQ100Y` | Yearly probability distribution (~$25 SPX brackets) |
| `KXINX` / `KXNASDAQ100` | Daily close brackets — filtered to soonest expiry |
| `KXINXMAXY` / `KXINXMINY` (+ QQQ analogs) | Year max/min one-touch cumulative probabilities |
| `KXFEDDECISION` | Next 3 FOMC meetings: hold / cut N bp / hike N bp |
| `KXRATECUTCOUNT` | 2026 total rate-cut count (0 cuts, 1 cut, ... 9 cuts) |
| `KXRECSSNBER` | NBER recession binary (2026 + 2027 events) |

### Polymarket Gamma API (no auth)
Endpoint: `gamma-api.polymarket.com/events?tag_slug=X&active=true&closed=false`

| Tag | Used for |
|---|---|
| `finance` | Monthly one-touch: "Will S&P 500 (SPX) hit $7,450 (HIGH) in June?" |
| `daily-close` | Daily "closes above $X" cumulative brackets (~$5 SPY strikes) |
| `daily-close` | Today's UP/DOWN binary (ETF version preferred over cash-index) |
| `fed` / `fed-rates` / `jerome-powell` | Next FOMC decision outcomes + 2026 cuts count |
| `big-tech` | "Largest company end of [period]" Mag 7 ranking |

## Data accuracy

Live API drift is real; this dashboard tries to surface clean numbers rather than raw probes. Specifically:

- **KXINX returns multiple expiries** in one call (today + Friday). Daily brackets chart filters to the soonest `close_time` only.
- **Polymarket cumulative is non-monotonic** under thin volume — e.g. `P(close ≥ $735) = 97%` and `P(close ≥ $740) = 98.5%` happens when the $740 bid is stale. The chart enforces right-to-left monotonicity before differencing, so brackets sum sensibly.
- **SPX/SPY ratio is computed live** from `^GSPC / SPY` (~10.02 with dividend drift), not hardcoded at 10.0, so Kalshi-SPX brackets and Polymarket-SPY brackets sit on the same x-axis.
- **SPY (SPY) vs S&P 500 (SPX) Up/Down**: when Polymarket lists both, the ETF version is preferred — it matches the spot price quoted in the header.
- **OI units**: Kalshi `open_interest_fp` is contract count (each contract pays at most $1). Reported as `N,NNN ctrs`, not USD.
- **Mag 7 placeholders** (`Company A..T`, `Other`) are filtered — only real tickers show.

See [commit `e2c1141`](https://github.com/YichengYang-Ethan/market-predict/commit/e2c1141) for the audit that surfaced these.

## Design notes

- **Hardcoded ticker map** ([`tickers.py`](market_predict/tickers.py)). Adding a ticker = one entry after verifying its Kalshi series has active markets. Explicit > clever.
- **Bracket parsing reads `yes_sub_title`**, not the ticker suffix. `KXINX-...-T9000` means "above 9000" but `KXINX-...-T4000` means "below 4000". Suffixes are not a reliable direction encoding.
- **Near-the-money walls**: call/put wall logic restricts to ±8% from spot. Absolute max OI often sits at deep-OTM crash hedges (e.g. SPY $580 puts when spot is $750), which are not tradable inflection points.
- **Gamma flip**: net dealer GEX (long-calls / short-puts convention) zero-crossing across a 41-point ±10% spot grid. ATM IV used uniformly across strikes — good enough for the flip level, not a full surface.
- **5-minute `st.cache_data` TTL** keeps the API call budget light. Refresh button clears it.

## Layout

```
┌───────────────────────────────────────────────────────────────────────┐
│ market-predict                                                          │
│ Ticker  [SPY ▾]                                              [Refresh]  │
├──────────┬──────────┬───────────┬────────┬─────────┬───────────────────┤
│  spot    │ S&P 500  │  ES fut   │  VIX   │ ATM IV  │   P/C OI          │
├──────────┴──────────┴───────────┴────────┴─────────┴───────────────────┤
│ Row 1:  3-month K-line + Volume        │ VIX 1m mini                  │
│ Row 2:  Options walls (OI bars)        │ Call wall / Put wall / γ flip │
│ Row 3:  Daily brackets (Kalshi + Poly) │ P(close UP) / P(open UP)     │
│ Row 4:  FOMC path  │ 2026 cuts (Kalshi) │ Next FOMC (Polymarket)      │
├────────────────────────────────────────────────────────────────────────┤
│ [Monthly] [Yearly] [Macro/Recession] [Mag 7] [2026 Cuts]              │
└────────────────────────────────────────────────────────────────────────┘
```

Color convention:
- 🟣 Kalshi data series — purple
- 🟡 Polymarket data series — gold
- 🔵 Spot price (vline / hline)
- 🟢 Call OI / call wall · 🔴 Put OI / put wall
- ⚫ Max pain dotted gray · 🟠 Gamma flip dotted orange

## Limitations

- yfinance options data is ~15 min delayed (fine for daily walls; not for intraday 0DTE)
- Kalshi yearly buckets are wide ($25 SPX / $50 NDX) — long tails carry mass outside the central display zone
- SPY/QQQ are ETFs; Kalshi only lists S&P 500 (`^GSPC`) and Nasdaq 100 (`^NDX`) cash-index contracts. ETF→index basis ignored
- No historical snapshots yet — coming in v0.2
- Polymarket low-volume strikes give noisy cumulative pricing; the monotonization fix smooths but does not eliminate this

## Roadmap

- **v0.2** — daily snapshot job (writes Parquet, seeds backtest data); BTC/ETH ticker support
- **v0.3** — Brier-score calibration of Kalshi vs realized outcomes (needs ~60 days of v0.2 snapshots first)
- **v0.4** — implied-distribution comparison: Kalshi probability vs option-IV-implied probability at same strike

## License

MIT
