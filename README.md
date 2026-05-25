# market-predict

Ticker-centric market context view for SPY/QQQ. Aggregates four data sources into one CLI snapshot:

- **Spot + underlying index** — yfinance (SPY → S&P 500, QQQ → Nasdaq 100)
- **Options walls** — call wall, put wall, max pain, gamma flip, ATM IV (from yfinance options chain)
- **Prediction-market distribution** — Kalshi yearly brackets (`KXINXY`, `KXNASDAQ100Y`)
- **Macro backdrop** — Fed path probabilities for next 3 FOMC meetings (`KXFEDDECISION`)

Everything runs on free public APIs — no auth keys, no paid subscriptions, zero maintenance cost.

## Quick start

```bash
git clone https://github.com/YichengYang-Ethan/market-predict
cd market-predict
pip install -e .
python -m market_predict SPY
python -m market_predict QQQ
```

## Sample output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  QQQ  $717.54   Nasdaq 100 (29,481.64)   2026-05-26 02:36
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Options walls (expiry 2026-06-18, 23d):
    Call wall:    $750  (37,609 OI)
    Put wall:     $680  (46,510 OI)
    Max pain:     $663
    Gamma flip:   $700
    ATM IV:       23.1%
    Total OI:     924,391 call / 1,310,432 put  (P/C=1.42)

  Kalshi Nasdaq 100 distribution (resolve 2026-12-31, 219d):
    P(         <19,000) =  10.0%  (OI $  925,308, vol24 $    37)
    P(   27,500-28,000) =   4.5%
    P(   28,000-28,500) =   2.5%
    P(   28,500-29,000) =   2.5%
    P(   29,000-29,500) =   2.5%  ← spot
    P(   29,500-30,000) =   1.5%
    P(   30,000-30,500) =   2.5%
    P(   30,500-31,000) =   2.5%
    P(         >33,000) =  45.5%
      shown coverage    74.0% (rest of distribution outside displayed range)

  Fed path (next 3 FOMC meetings):
    KXFEDDECISION-26JUN (close 2026-06-17):
      Fed maintains rate         =  96.5%  (OI $2,088,387)
      ...
```

## Why these data sources

| Need | Source | Why |
|---|---|---|
| Spot + history | yfinance | Free, no key, well-known schema |
| Options chain (OI, IV) | yfinance | Free OPRA data for liquid US tickers |
| Prediction-market view | Kalshi public API | No auth needed for market reads; `KXINXY`/`KXNASDAQ100Y` have OI $2M+ |
| Macro / Fed | Kalshi `KXFEDDECISION` | Kalshi's flagship product — OI $8.6M, vol24 $350k+ |

Polymarket has effectively no SPY/QQQ contracts (tag list contains no equity-index categories), so it is not integrated for this MVP. BTC/ETH support is planned for v0.2 and will include Polymarket alongside Kalshi.

## Design notes

- **Hardcoded ticker map** ([`tickers.py`](market_predict/tickers.py)) — explicit > clever. Adding a ticker = appending one entry after verifying the corresponding Kalshi series has active markets.
- **Bracket parsing via `yes_sub_title`** — Kalshi ticker suffixes (`T9000`, `T4000`) do not encode direction consistently. `T9000` means "above 9000" but `T4000` means "below 4000". Only the sub-title is reliable.
- **Near-the-money walls** — call/put wall logic intentionally restricts to ±8% from spot, since absolute max OI usually sits at deep-OTM crash hedges (e.g. SPY puts at $580 when spot is $745) which are not tradable inflection points.
- **Gamma flip** — net dealer GEX (long calls / short puts convention) zero-crossing across a 41-point spot grid.

## Limitations (known, MVP scope)

- yfinance options data has ~15 min delay — fine for daily walls, insufficient for intraday 0DTE
- Kalshi yearly brackets ($200-wide buckets) cover ~70% of distribution mass when zoomed near spot — long tails on either side carry the rest
- No historical snapshots yet — coming in v0.2 (daily Parquet write to seed backtest data)
- SPY/QQQ are ETFs; Kalshi only has S&P 500 (`^GSPC`) and Nasdaq 100 (`^NDX`) index contracts. ETF→index basis is small and ignored.

## Roadmap

- **v0.2** — daily snapshot job (writes Parquet for backtest seeding), BTC/ETH support (Kalshi + Polymarket)
- **v0.3** — historical Brier score for Kalshi probability calibration (needs ~60 days of snapshots first)
- **v0.4** — implied distribution comparison: Kalshi probability vs option-IV-implied probability at same strike

## License

MIT
