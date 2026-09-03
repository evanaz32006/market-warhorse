# market-warhorse — V0 Build Spec (submission-ready)

Build V0 of a swing-trade ranking and self-evaluation system called **market-warhorse**.

## Goal
A stats-only stock ranking and tracking tool using free price/volume data. No AI summaries, no broker connection, no trade execution, no buy/sell commands. The system calculates technical/price/volume stats for a watchlist, ranks stocks across multiple time horizons, saves daily score snapshots, **backfills its own history on first run**, and evaluates whether high scores actually predicted outperformance versus a benchmark.

This is **not** a proven trading model. It is a research framework whose entire purpose is to save enough history to prove (or disprove) whether its own scores work. Every parameter below is a transparent, testable default — not a law. The evaluation loop exists to tell us which ones earn their place.

---

## DECISIONS LOG (parameters set for V0 — all are testable defaults, not facts)
These were undefined or vague in the original draft and are now pinned. Treat them as v0.1 assumptions on record; later model versions may change them based on evaluation output.

1. **`return_10d_percentile`, `return_252d_percentile`** — now included in the cross-sectional percentile set (were used but undefined).
2. **`distance_from_52w_high_adjusted_percentile`** — defined as: rank so closer-to-high = higher percentile, then **cap at 50 for any ticker with `extended_flag = True`** (neutralizes the near-high bonus when stretched).
3. **`near_20d_high`** — `latest_close >= 0.98 * (max high of last 20 sessions)` (within 2%).
4. **`near_60d_high`** — `latest_close >= 0.97 * (max high of last 60 sessions)` (within 3%).
5. **`pullback_above_SMA50`** — `latest_close > SMA50` AND close is **between 3% and 10% below** the 20-session high (controlled pullback, trend intact).
6. **`failed_breakout_flag`** — a new 20-session high was set **within the last 5 sessions** AND `latest_close` is now **≥3% below** that high.
7. **"benchmark vol very high"** — `benchmark_volatility_20d` is above the **80th percentile** of its own trailing 252-session distribution of 20d vol.
8. **Volatility** — stdev of daily simple returns over the window × **√252** (annualized).
9. **`downside_volatility_20d`** — stdev of daily returns **< 0 only** over trailing 20 sessions × √252 (semideviation).
10. **`up_volume_vs_down_volume_20d`** — `sum(volume on up days) / sum(volume on down days)` over last 20 sessions; if down-volume sum is 0, cap ratio at **10.0**.
11. **`ATR14`** — 14-session simple rolling mean of True Range, where TR = `max(high-low, abs(high-prev_close), abs(low-prev_close))`.
12. **`max_drawdown_20d` / `max_drawdown_60d`** — maximum peak-to-trough % decline over the window, stored as a **positive magnitude** (e.g., 12.0 = a 12% drawdown).
13. **`evaluation.py`** joins forward returns by **real trading date**, re-fetched from price history — never by snapshot row position. (See Performance tracking.)
14. **Backfill mode** reconstructs point-in-time scores over the full available history on first run. (See Backfill.)

---

## Tech stack
Python 3.11+, pandas, numpy, yfinance, matplotlib, SQLite (stdlib `sqlite3`), terminal + CSV output for V0.

## Project structure
```
market-warhorse/
├── app.py
├── watchlist.csv
├── requirements.txt
├── data/
│   └── market_data.db
├── output/
│   ├── latest_rankings.csv
│   ├── score_history.csv
│   └── performance_review.csv
└── src/
    ├── data.py
    ├── features.py
    ├── scoring.py
    ├── storage.py
    ├── evaluation.py
    └── utils.py
```

### Environment bootstrap (app.py must handle on first run)
- `requirements.txt` is human-authored and version-pinned (do NOT generate it at runtime).
- `app.py` must create `data/` and `output/` directories if missing, and initialise the SQLite schema if the DB does not exist. The project must be runnable on a fresh machine with only `pip install -r requirements.txt` + `python app.py` — no manual directory creation or DB setup.
- Add `src/` to `config.py` contains all tunable values. Examples of the style required:

```python
# config.py
PARAMS = {
    "model_version": "v0.1_price_volume_only",
    ...
}

SCORE_WEIGHTS = {
    "score_20d": {
        "trend":            0.20,
        "momentum_20d":     0.20,
        "relative_strength_20d": 0.20,
        "volume_behavior":  0.10,
        "risk":             0.15,
        "setup":            0.10,
        "market_regime":    0.05,
    },
    ...
}

EARNINGS_PENALTIES = {
    "5d": 20, "20d": 12, "60d": 5, "120d": 0
}
```

Future model versions must be able to change `config.py` values without touching `scoring.py` logic.

---

## Inputs
`watchlist.csv` with columns: `ticker, sector, benchmark, notes`.
Benchmark resolution per ticker: use the ticker-specific benchmark from the CSV if provided; semiconductor names should use `SMH`; otherwise default to `QQQ`. Index/ETF rows benchmark to `SPY`.

### Recommended default watchlist (expanded for evaluation power)
The original 20-name list is heavily correlated (one semis bet + one megacap-tech bet), which cripples the statistical power of the evaluation loop. This expanded ~55-name universe across 6 sectors gives the IC/correlation metrics real breadth. **You can still trade only your core names — this universe is for measurement.** Benchmarks are sector ETFs so relative strength is measured against the right peer group.

```
ticker,sector,benchmark,notes
NVDA,Semiconductors,SMH,core
AVGO,Semiconductors,SMH,core
MU,Semiconductors,SMH,core
TSM,Semiconductors,SMH,
AMD,Semiconductors,SMH,
ARM,Semiconductors,SMH,
QCOM,Semiconductors,SMH,
TXN,Semiconductors,SMH,
LRCX,Semiconductors,SMH,
AMAT,Semiconductors,SMH,
KLAC,Semiconductors,SMH,
MRVL,Semiconductors,SMH,
ADI,Semiconductors,SMH,
ON,Semiconductors,SMH,
MSFT,Tech-Software,QQQ,watchlist
GOOGL,Tech-Software,QQQ,watchlist
AMZN,Tech-Software,QQQ,
META,Tech-Software,QQQ,
ORCL,Tech-Software,QQQ,
NOW,Tech-Software,QQQ,core
CRM,Tech-Software,QQQ,
CRWD,Tech-Software,QQQ,
PLTR,Tech-Software,QQQ,
PANW,Tech-Software,QQQ,
ADBE,Tech-Software,QQQ,
SNOW,Tech-Software,QQQ,
VRT,Industrials-Power,XLI,core
ETN,Industrials-Power,XLI,
GEV,Industrials-Power,XLI,
PWR,Industrials-Power,XLI,
CEG,Utilities-Power,XLU,nuclear
VST,Utilities-Power,XLU,nuclear
NEE,Utilities-Power,XLU,
DUK,Utilities-Power,XLU,
SO,Utilities-Power,XLU,
JPM,Financials,XLF,
GS,Financials,XLF,
MS,Financials,XLF,
BAC,Financials,XLF,
V,Financials,XLF,
MA,Financials,XLF,
LLY,Healthcare,XLV,
UNH,Healthcare,XLV,
JNJ,Healthcare,XLV,
ABBV,Healthcare,XLV,
MRK,Healthcare,XLV,
XOM,Energy,XLE,
CVX,Energy,XLE,
COP,Energy,XLE,
SLB,Energy,XLE,
SMH,Index,SPY,benchmark
QQQ,Index,SPY,benchmark
XLI,Index,SPY,benchmark
XLU,Index,SPY,benchmark
XLF,Index,SPY,benchmark
XLV,Index,SPY,benchmark
XLE,Index,SPY,benchmark
SPY,Index,SPY,benchmark
```

## Data
- Use yfinance to download daily OHLCV with `period="2y"` and `auto_adjust=True` for each ticker and each unique benchmark.
- **yfinance rate-limit hardening (mandatory).** Yahoo's unofficial endpoints enforce roughly 360 requests/hour and will rate-limit or temporarily IP-block on heavy/rapid use. The code MUST:
  - Download in **batches** (5–10 tickers per `yf.download` call) with a configurable delay (~1.5s) between batches.
  - Wrap every download in **retry-with-exponential-backoff** (≥3 retries) that catches `YFRateLimitError` and generic exceptions; one failed ticker logs and is skipped, never crashes the run.
  - **Cache OHLCV to SQLite** (`price_history` table) and on each subsequent run fetch only the **incremental missing dates** rather than re-pulling 2y every time — this is the single biggest rate-limit saver and the maintainer's own recommended pattern.
  - Print a fetch summary: counts fetched fresh / served from cache / failed.
  - Pin yfinance in `requirements.txt` so it can be upgraded when Yahoo changes its backend.
- Save data with `timestamp_fetched`.
- Handle missing/failed tickers gracefully — log and skip, never invent data.
- Never use future data when calculating a score for a given date (strict no-lookahead — critical for backfill).

## Earnings date
- Try to pull the next earnings date from yfinance; compute `days_until_earnings`.
- If unavailable, set `days_until_earnings = null` and `earnings_date_missing = True`.
- Never invent earnings dates. **In backfill mode the earnings penalty is always skipped** (historical `days_until_earnings` is not reconstructable from yfinance) — set `earnings_risk_unknown = True` for backfilled rows.

---

## Raw features (per ticker, computed as-of the evaluation date)

**Price/trend:** `latest_close`, `SMA20`, `SMA50`, `SMA200`, and the percent-distance fields `close_vs_SMA20_pct`, `close_vs_SMA50_pct`, `close_vs_SMA200_pct`, `SMA20_vs_SMA50_pct`, `SMA50_vs_SMA200_pct` (all `((a-b)/b)*100`).

**Momentum:** `return_1d, return_5d, return_10d, return_20d, return_60d, return_120d, return_252d` (252 only if enough data; else null).

**Relative strength:** `benchmark_return_{5,20,60,120}d`; `relative_strength_{5,20,60,120}d = return_Nd - benchmark_return_Nd`.

**Volume/behaviour:**
- `volume_ratio_20d = latest_volume / avg_volume_20d`; `volume_ratio_60d` likewise.
- `high_volume_up_days_20d` = count of last-20 sessions where `daily_return > 0` and `volume > 1.5 ×` that ticker's rolling 20d avg volume; `high_volume_down_days_20d` likewise with `daily_return < 0`.
- `up_volume_vs_down_volume_20d` = `sum(vol on up days)/sum(vol on down days)` over last 20 sessions; cap at 10.0 if denominator is 0.
- `close_position = (Close - Low)/(High - Low)`; if `High == Low`, set 0.5.
- `weak_close_flag` if `close_position < 0.35`; `strong_close_flag` if `close_position > 0.65`.

**Risk:**
- `ATR14` (14-session mean of True Range as defined in Decisions Log #11); `ATR_pct = ATR14 / latest_close`.
- `volatility_20d`, `volatility_60d` — annualized stdev of daily simple returns (× √252).
- `downside_volatility_20d` — annualized semideviation of negative daily returns over 20 sessions.
- `max_drawdown_20d`, `max_drawdown_60d` — positive-magnitude peak-to-trough % over the window.
- `distance_from_52w_high_pct = ((52w_high - latest_close)/52w_high)*100`.
- `distance_from_52w_low_pct = ((latest_close - 52w_low)/52w_low)*100`.

**Setup flags:** `near_20d_high`, `near_60d_high`, `not_extended_flag`, `extended_flag`, `pullback_above_SMA50`, `failed_breakout_flag` — all per the Decisions Log definitions.

**Market/sector regime (per benchmark):** `benchmark_above_SMA20/50/200`, `benchmark_return_20d`, `benchmark_return_60d`, `benchmark_volatility_20d`, plus a `benchmark_vol_high_flag` (True if `benchmark_volatility_20d` > 80th percentile of its own trailing 252-session 20d-vol distribution).

---

## Percentile ranks (intra-watchlist, 0–100, per run)
Compute cross-sectional percentile ranks across all watchlist tickers present on that run for:
`return_5d, return_10d, return_20d, return_60d, return_120d, return_252d`*, `relative_strength_{5,20,60,120}d`, `volume_ratio_20d`, `ATR_pct` (inverted — lower risk ranks higher), `volatility_60d` (inverted), `max_drawdown_60d` (inverted), and `distance_from_52w_high_adjusted_percentile`.

*Tickers lacking `return_252d` are excluded from that one percentile's ranking pool; components using it fall back per their rules.

**`distance_from_52w_high_adjusted_percentile`:** rank tickers so smaller distance-from-high → higher percentile; then for any ticker with `extended_flag = True`, **cap its value at 50**.

---

## Component scores (0–100, each saved beside the final score)

**trend_component:** +20 each for `close>SMA20`, `close>SMA50`, `close>SMA200`, `SMA20>SMA50`, `SMA50>SMA200`. Clamp 0–100.

**short_momentum_component:** 40% `return_5d_pct` + 35% `return_10d_pct` + 25% `return_20d_pct`; −15 if `return_5d<0`; −10 if `return_10d<0`. Clamp.

**momentum_component_20d:** 50% `return_20d_pct` + 30% `return_60d_pct` + 20% `return_10d_pct`; −20 if `return_20d<0`. Clamp.

**medium_momentum_component:** 45% `return_60d_pct` + 35% `return_120d_pct` + 20% `return_20d_pct`; −20 if `return_60d<0`. Clamp.

**long_momentum_component:** 45% `return_120d_pct` + 35% `return_252d_pct` (fallback to `return_120d_pct` if 252 missing) + 20% `return_60d_pct`; −20 if `return_120d<0`. Clamp.

**relative_strength_component_5d:** 60% `rs_5d_pct` + 40% `rs_20d_pct`; −10 if `rs_5d<0`. Clamp.
**relative_strength_component_20d:** 50% `rs_20d_pct` + 50% `rs_60d_pct`; −10 if `rs_20d<0`; −10 if `rs_60d<0`. Clamp.
**relative_strength_component_60d:** 60% `rs_60d_pct` + 40% `rs_120d_pct`; −10 if `rs_60d<0`. Clamp.
**relative_strength_component_120d:** 70% `rs_120d_pct` + 30% `rs_60d_pct`; −10 if `rs_120d<0`. Clamp.

**volume_behavior_component:** start 50; if `vol_ratio_20d>1.2 & return_1d>0` +10; if `>1.5 & return_1d>0` +15 more; if `>2.0 & return_1d>0` +10 more; if `>1.5 & return_1d<0` −25; if `>2.0 & return_1d<0` −15 more; add `5*(high_vol_up_days - high_vol_down_days)`; if `weak_close_flag & vol_ratio_20d>1.2` −10; if `strong_close_flag & vol_ratio_20d>1.2` +10. Clamp.

**risk_component:** 35% `ATR_pct_inv_pct` + 25% `volatility_60d_inv_pct` + 25% `max_drawdown_60d_inv_pct` + 15% `distance_from_52w_high_adjusted_percentile`; −20 if `extended_flag`; −15 if `close<SMA50`. Clamp.

**setup_component:** start 0; +20 `close>SMA20`; +20 `close>SMA50`; +20 `not_extended_flag`; +15 `near_20d_high`; +15 `near_60d_high`; +10 `pullback_above_SMA50`; −30 `failed_breakout_flag`. Clamp.

**market_regime_component:** +25 `benchmark_above_SMA20`; +25 `benchmark_above_SMA50`; +20 `benchmark_above_SMA200`; +15 if `benchmark_return_20d>0`; +15 if `benchmark_return_60d>0`; −10 if `benchmark_vol_high_flag`. Clamp.

**Event risk penalty (live runs only):** if `0 <= days_until_earnings <= 5`: penalty_5d=20, penalty_20d=12, penalty_60d=5, penalty_120d=0. If unknown, no penalty and set `earnings_risk_unknown=True`.

---

## Horizon scores (clamp each 0–100)
- **score_5d:** trend 10% + short_momentum 25% + rs_5d 15% + volume_behavior 20% + risk 15% + setup 15% − penalty_5d.
- **score_20d:** trend 20% + momentum_20d 20% + rs_20d 20% + volume_behavior 10% + risk 15% + setup 10% + market_regime 5% − penalty_20d.
- **score_60d:** trend 25% + medium_momentum 20% + rs_60d 25% + volume_behavior 5% + risk 15% + market_regime 10% − penalty_60d.
- **score_120d:** trend 30% + long_momentum 25% + rs_120d 25% + risk 10% + market_regime 10% − penalty_120d.

**Labels:** 80–100 strong / 65–79 decent / 50–64 watchlist / <50 weak.

---

## Validation and fail-loud requirements

The system must **fail loudly rather than silently producing bad scores.** Create a validation layer (can live in `utils.py`) that runs checks at key pipeline stages and raises clear warnings or errors, never swallowing problems.

**Data integrity checks (run after fetching):**
- Warn if duplicate `(ticker, date)` rows exist in price data.
- Warn if benchmark data is missing for any ticker's assigned benchmark.
- Warn if a ticker has insufficient history for a required window (e.g. fewer than 252 bars when computing `return_252d`).

**Feature checks (run after features.py):**
- Raise a warning if any feature column produces `NaN` unexpectedly for a ticker with sufficient data.
- Log which tickers had features set to null and why.

**Score checks (run after scoring.py):**
- Raise a warning if any horizon score is `NaN` after clamping.
- Raise a warning if any component score is outside [0, 100] before clamping (indicates a formula logic error).

**Evaluation checks (run in evaluation.py):**
- Raise a warning if forward-return calculations produce `NaN` or `inf` values.
- Raise an error if a forward-return join produces rows where the result date precedes the snapshot date (indicates a date-join bug — the single most dangerous silent failure mode).

**Create unit tests for:**
- SMA calculations against manually-verifiable values.
- Return calculations (1d, 5d, 20d) against known price sequences.
- ATR calculation against a hand-computed example.
- Percentile ranking (confirm inverted percentiles invert correctly).
- Relative strength (confirm `rs = stock_return - benchmark_return`).
- Forward return calculation (confirm D+5 is actually 5 trading days, not 5 calendar days).
- Max drawdown calculation against a known sequence.

---

## Storage (SQLite `market_data.db`)
One row per daily run with a UNIQUE constraint on `(run_date, ticker, model_version)`. Store: `run_date, timestamp_fetched, ticker, benchmark, latest_close, <all raw features>, <all component scores>, score_5d, score_20d, score_60d, score_120d, backfilled (bool), earnings_risk_unknown (bool), model_version = "v0.1_price_volume_only"`. Also export `output/latest_rankings.csv` and `output/score_history.csv`.

---

## Backfill mode (`python app.py --backfill`) — run once on setup
Reconstruct point-in-time scores for **every trading date** in the available 2y history so the evaluation loop has data immediately instead of in 6 months.

- For each historical date D, compute all features using **only** data up to and including D. Rolling windows end at D; percentile ranks are computed cross-sectionally across the watchlist **as of D**. Strict no-lookahead.
- Skip the earnings event-risk penalty (set `earnings_risk_unknown=True`); mark rows `backfilled=True`.
- Write all reconstructed snapshots to the DB, then run evaluation over the full history.
- Subsequent daily runs (`python app.py`) append one fresh live snapshot per ticker and include the earnings penalty.

> The longest horizon (120d) only becomes evaluable once 120 trading days of *forward* data exist past a snapshot. Backfill gives you ~1.5 years of already-elapsed history, so 5d/20d/60d scores are evaluable on day one and a large chunk of 120d scores too.

---

## Performance tracking (`evaluation.py`)
For every stored snapshot (date D, ticker T), compute forward returns **by real trading date**, not by row position.

- Re-fetch (or reuse cached) actual daily price history per ticker. Locate D in T's real trading-day series; `future_return_Nd = close[D+N] / close[D] - 1` where D+N is N **trading days** after D in that ticker's own series. **Critical:** never use `shift(-N)` across a mixed-ticker table by row order — always resolve forward dates within each ticker's date-indexed price series (equivalently `groupby(ticker)` on a per-ticker date-sorted frame). One ticker's rows must never bleed into another's.
- Compute the benchmark's forward returns the same way for T's assigned benchmark.
- Derive: `future_return_{5,20,60,120}d`, `future_benchmark_return_{5,20,60,120}d`, `future_excess_return_{5,20,60,120}d`, `max_drawdown_after_20d`, `max_drawdown_after_60d`.
- **Guardrail:** exclude any snapshot from a horizon's metrics if D+N has not yet occurred (no evaluating last week's 20d score).

### Performance report (`output/performance_review.csv`)
By score bucket (the label bands): average & median future excess return, hit rate (% beating benchmark), average max drawdown. Plus: component correlations with future excess returns, Spearman rank correlation / information coefficient where computable, top overperforming components, weakest components, whether high-score stocks beat their benchmark, and **suggested** weight changes (never auto-applied).

---

## Model versioning
`model_version = "v0.1_price_volume_only"`. Weights never auto-change. Structure code so new versions (`v0.2_adjusted_relative_strength`, `v0.3_adjusted_risk_penalty`, `v1.0_earnings_revisions_added`) are easy to add and run side-by-side against the same history.

## Outputs
1. Print a clean ranked terminal table sorted by `score_20d` desc.
2. `output/latest_rankings.csv` — all fields + scores.
3. `output/score_history.csv` — all stored snapshots.
4. `output/performance_review.csv` — when forward data exists.

## Future universe expansion (V0 note — no implementation required now)
The ranking engine must not assume a fixed watchlist forever. Future versions should support pluggable universes: user watchlist (V0), semiconductor universe, Nasdaq 100, S&P 500. Design the scoring and evaluation pipeline so the input is a dataframe of tickers+benchmarks, not a hardcoded list — swapping the universe should require changing only `watchlist.csv` (or a future config flag), not rewriting logic.

---

## Rules
Modular, readable, heavily commented. Handle missing data gracefully without inventing numbers. No AI summaries, no trade execution, no broker connection, no buy/sell commands. Research and ranking only.

## Deliverable
A working project that runs with:
```
pip install -r requirements.txt
python app.py --backfill   # once, to bootstrap history
python app.py              # daily
```
