# HANDOFF — market-warhorse
**Written 2026-09-16. Updated 2026-09-16 (later the same day) with the results of items 1-3.**

> ## STATUS UPDATE — items 1, 2 and 3 are done or in flight. Read this box before the plan below.
>
> **Item 1 (live model != backtested model): FIXED and PROVEN.** There were THREE divergences, not
> one — the third was a near-earnings penalty applied to 289 live rows that no backfilled row could
> match. All three had a single cause and are fixed as v0.6 via one shared
> `app.edgar_fundamentals_resolver`. Proof, not assertion: both code paths run over 1,526 tickers on
> 2026-08-19, 33 fields each, **zero differences**. Guarded by `tests/test_live_backfill_parity.py`,
> and both load-bearing assertions were confirmed by mutation (one of them initially could not fail).
>
> **The v0.6 backfill CANNOT be shortcut by copying v0.5's rows.** Tried it; 1,519 of 1,525 names
> differ while `latest_close` matches exactly. The closes did not move, the history behind them did —
> the gap repair refilled 2,069 interior bars and every trailing-window feature spanning a hole
> changed. `--backfill-v06` is the way, ~6 hours, resumable. It covers through 2026-09-15, so v0.6's
> true out-of-sample starts the day after it lands — a clean holdout, which is part of problem #3.
>
> **Item 2 (survivorship): MEASURED, and it cuts the OPPOSITE way to what this document assumed.**
> Point-in-time membership is reconstructed from Wikipedia *revisions* (the "Selected changes" table
> is gone from the page entirely — do not go looking for it). 231 names were in the S&P 1500 during
> the window and never scored: 3.4% of the S&P 500, 8.9% of the 400, **21.7% of the 600**. Of those,
> 131 are unrecoverable — but they exited by ACQUISITION, at a premium, so losing them biases a
> measured edge *downward*. The 100 recoverable ones were RELEGATED, and they returned **-14.46%**
> forward-120d against **+7.18%** for the names the model could see, negative in 22 of 22 months.
> Since the headline claim is "top 10 beat the AVERAGE STOCK by +10.4%", restoring these names LOWERS
> that baseline and makes the reported edge *larger*. Survivorship inflates the thing being beaten.
> Caveats kept honest: only ~4 independent 120-day windows (sign test p=0.0625), and the gap is a
> lower bound since relegated-then-bankrupt names have no price history either.
>
> **Does it reach the picks?** Thinly. Ranked on trailing 120d relative strength across 573
> name-months, the missing names average the 30th percentile, but 0.87% (5) reach the top-10 region —
> HTZ in May-Jul 2025, GOGO in Jul-Aug 2025. Roughly 2% of pick-slots should have gone to a name the
> model could not see, and both offenders are the same failure mode: a violent momentum spike that
> reverses into relegation. Settling the pick side needs the widened-universe backfill.
>
> **Item 3 (estimate revisions): COLLECTOR IS LIVE.** `estimate_history`, append-only, point-in-time
> gated in SQL, rolling ~1/5 of the universe nightly. DELIBERATELY NOT SCORED — a test fails the
> build if an estimate field reaches a weight map, because scoring a live-only input is exactly the
> mistake v0.6 undid. Useful discovery: `eps_trend` carries its own 7/30/60/90-day trail, so each
> fetch yields five points, not one.
>
> **Other things found while verifying, all committed:**
> - Recovered days were stamping TODAY's fundamentals onto a past date. Now resolved as-of themselves.
> - "Frozen" versions silently stopped maturing. A forward return is not known until D+120 has
>   ELAPSED, so a version with no new snapshots still gains evaluable rows nightly; v0.4's metrics
>   had been pinned to 2026-08-21 and carried forward unlabelled. Now skipped only when genuinely
>   exhausted, otherwise refreshed one per night, with `recomputed_on` on every report row.
> - `edgar._facts_as_of` read 20,935 facts/ticker on its SQL route vs 1,894 on its index route for
>   the identical answer. Tag-filtered: 7.7x faster, 0 field differences.
> - **`ev_to_ebitda` and `operating_margin` are NULL on 100% of all 1,055,667 EDGAR rows and always
>   have been.** Both deliberate and documented, but it means `value_percentile` is the mean of
>   THREE ratios, not the four config advertises, and quality has never included operating margin.
>
> **Still true and still unaddressed:** the 14.1 GB DB has never been backed up, and with 25 GB free
> on C: a local copy will not fit. Task Scheduler still kills the run on battery.


**Read this first, then CLAUDE.md, then SESSION_STATE.md. This file is the mission brief; the
others are the rules and the log.**

---

## Your job

This is a 1,500-name quantitative equity research system built by a high-school student, alone,
over three months. It works — 303 tests, 14.1 GB of point-in-time data, unattended nightly runs,
five immutable model versions. What it has **not** done is find a tradeable edge.

The previous assistant concluded the search space was "exhausted." **That conclusion was wrong and
the owner correctly rejected it.** Seven experiments were run, but across only **TWO data sources**:
price/volume, and SEC filings. The entire universe of alternative data is untouched. Your job is to
find signal in the sources nobody has looked at yet, and to fix the three structural problems that
would make any signal you find untrustworthy.

Do not re-litigate whether the project is worth doing. It is. Build.

---

## Ground truth: what is actually known

**The one positive result.** At a ~120-trading-day horizon, the top 10 names by `score_120d` beat
the average stock by +10.4% and beat SPY in 4 of 9 cost-charged backtest configurations, with
Sharpe 1.28–1.38 vs SPY's 1.06 and max drawdown −11.6% vs −18.8%. **8 of 9 configs beat SPY on
risk-adjusted return.** The demonstrated result is "index-like returns with ~40% less drawdown,"
not "beats the market."

**The seven nulls** (all pre-registered, all correctly measured — do not redo these):
seasonality/day-of-week, SEC Form 4 insider transactions, 8-K item codes, SUE/post-earnings drift,
short-term reversal, sector momentum (2.2y AND 27y of ETF history), sector breadth. Five had
adequate power and found nothing. Two (insider, short-window sector) were underpowered — the
minimum detectable effect exceeded the published effect size, so they are "cannot tell," not "no."

**Everything below ~40 trading days is empty** for price-derived features across large, mid and
small caps. That finding is solid and repeatedly confirmed. Short-horizon work needs genuinely new
inputs, not better weights.

---

## THREE STRUCTURAL PROBLEMS — fix these before trusting any new result

### 1. The live model is not the backtested model. THIS IS THE WORST ONE.

Verified 2026-09-16 by direct query:

| | live rows (27,396) | backfilled rows (777,738) |
|---|---|---|
| `fundamentals_pit` | **0** on every row | **1** on every row |
| fundamentals source | yfinance *current* snapshot | EDGAR point-in-time |
| `short_interest_component` | present | **NULL on all 777,738** |
| `profit_margin` NULL | 864 | 116,804 |

Every historical number — the +6.4% decile spread, the backtest, the daily log's "Simulated: same
model" caption — describes a model that **is not the one running nightly.** The nightly model has
never been validated. The fundamentals differ in definition, not just vintage (EDGAR operating
margin ran 0.81× yfinance's across unrelated sectors; debt includes lease obligations, yfinance's
does not).

**Fix:** make the nightly run resolve fundamentals through `edgar.get_fundamentals_as_of(as_of=D)`
— the code already exists and is used by the backfill — and either drop `short_interest_component`
or source a backfillable history (FINRA publishes free bi-monthly). Then re-run everything. This is
a new `model_version` under CLAUDE.md #5.

### 2. Survivorship bias has never been measured, and may be the entire edge.

The universe is **today's** S&P 1500 projected backwards to 2024-06. A trend/value strategy on
survivors-only inflates exactly this way — survivors are the names that trended. Every output row
is stamped `survivorship_biased=True` and the magnitude has never once been quantified.

Only 6 names died while tracked (EA, WBS, EQR, AVB, LEG, HLX). The real bias is names that were in
the index in 2024 and were dropped before the 2026-08 expansion — never added, never scored.

**Fix:** reconstruct point-in-time index membership. Wikipedia's "List of S&P 500 companies" has a
second table of historical adds/drops (a parse attempt on 2026-09-16 failed — the page's table
layout changed; retry with a more tolerant parser, or use a public constituent-history dataset).
Re-run the 120d test on the true as-of universe. **Until this is done the +10.4% is an upper bound,
not an estimate.** Everything else should wait on this.

### 3. No project-level holdout.

The 120-day horizon, the display choice, the weight review — all chosen while looking at the full
2.2 years. Multiple comparisons are corrected *within* each family (BH-FDR, circular-shift nulls),
but the project as a whole is a ~500-cell search and the 120d finding came out of searching
horizons. The only true out-of-sample is the 18 live days since 2026-08-20, which are scored by the
wrong model per problem #1.

**Fix:** freeze a holdout period now and never look at it until a candidate is final.

---

## THE ACTUAL OPPORTUNITY: sources nobody has touched

Ranked by (documented effect size) × (free) × (fits the existing point-in-time architecture).

### Tier 1 — strong prior, free, no new infrastructure

**1. Analyst estimate revisions.** The single strongest documented anomaly not yet tried here, and
the previous assistant never once tested it. Upward EPS-estimate revisions predict returns at 1–6
months with published IC well above anything price-derived. Partially available free via
yfinance (`Ticker.analyst_price_targets`, `.recommendations`, `.earnings_estimate`) — the catch is
these are **current-snapshot only, not historical**, so they can only be accumulated forward from
today, not backfilled. Start collecting NOW in the nightly run so a history exists in six months.
This is the highest-value thing on the list and it costs one column and patience.

**2. Filing TEXT via LLM extraction.** `src/filing_text.py` is BUILT and tested (14 tests) but
never run — it needs an `ANTHROPIC_API_KEY`. The 8-K null was a null on *two-digit item codes*;
item 8.01 is literally titled "Other Events." Reading what the filings *say* is a different
experiment. The module extracts facts only (no sentiment field exists — a test fails the build if
one is added) and has a contamination test built in: results split at the model's knowledge cutoff,
because an LLM knows what happened after the filings it trained on. Pilot ≈ $5 for 2,000 filings,
full sample ≈ $120. 48,964 8-Ks available, 19,578 pre-cutoff / 29,386 post — both halves large
enough to conclude.

**3. Options-derived signals.** Put/call ratio, implied-volatility skew, and IV rank are well
documented and free-ish via yfinance `Ticker.option_chain`. Same limitation as #1: current-only, so
start accumulating. IV skew in particular carries information price history does not.

**4. FINRA short interest history.** Free, bi-monthly, backfillable. Would resurrect
`short_interest_component`, which is currently dead weight (NULL on all 777k backfilled rows) and
still carries 7% of the 20-day score's weight.

### Tier 2 — free, needs a pipeline

**5. Macro / regime data.** FRED (free API, decades of history, perfectly dated): yield-curve
slope, credit spreads, VIX term structure, unemployment claims. The existing
`market_regime_component` is one ETF's SMA position and has negative IC. Real regime data is a
different thing, and it is the input class most likely to fix the sector/market-timing gap that
sector-neutral ranking structurally creates.

**6. GDELT news volume and tone.** Free, timestamped, backfillable via API. The defensible entry
point into news sentiment — unlike social scraping, it is reproducible.

**7. Google Trends.** Free, weekly, backfillable. Search-volume spikes on a ticker or product have
documented short-horizon predictive content.

### Tier 3 — the owner's specific asks, honestly assessed

**Trump / political social posts.** The owner has asked for this repeatedly and it has been
deflected twice. Take it seriously: political-shock effects on markets are real and large. The
honest constraints are that Truth Social has no free stable API, X's is paid, and — the real
problem — impact lives at minute resolution while this system runs on daily bars. **If pursued, the
right framing is not per-post sentiment but event-day dummies** (does the index behave differently
on days with high political-news volume?), which GDELT can supply reproducibly. Do not scrape.

**Paid data.** If the owner will spend: Financial Modeling Prep or Polygon (~$30–100/mo) give
historical estimate revisions and options history with real point-in-time depth. That single
purchase would unlock #1 and #3 as *backfillable* rather than accumulate-forward. This is the
highest-leverage money in the project.

---

## Rules that are not negotiable

From CLAUDE.md, and every one of them has caught a real bug here:

1. **No lookahead.** Features as of D use only data through D. Forward returns join on real trading
   dates within each ticker's own series. EDGAR gates on `filed_date <= D`. 8-K events gate on an
   *acceptance-time-adjusted* effective date (a filing accepted at 16:35 ET is not tradeable that
   day).
2. **Never invent data.** Missing → `null` plus a flag, never 0. A data gap and a real zero are
   different facts; conflating them manufactured a "no insider activity" signal out of a
   publication lag.
3. **All tunables in `config.py`.**
4. **Versioned history is immutable.** New logic = new `model_version`, run side by side.
5. **Pre-register the reading before looking.** State what result would confirm the hypothesis,
   what would falsify it, and what the minimum detectable effect is — BEFORE running. This is the
   discipline that has kept every null honest.
6. **Report the minimum detectable effect next to every null.** "No signal found" and "no signal
   this sample could have seen" are different claims. Two of the seven nulls are the latter.

---

## Tools already built that you should use, not rebuild

- `src/patterns.py` — conditional-pattern harness. "After X, does Y happen?" as a query.
  Bonferroni + BH-FDR + circular-shift family null + Student-t p-values + minimum detectable effect.
- `src/research.py` — decay curves, walk-forward weight fitting, quality decomposition, insider IC,
  8-K event study, sector timing (short and 27-year). ~2,000 lines.
- `src/backtest.py` — portfolio simulation, fills at D+1 open, spread + square-root market impact.
- `src/filing_text.py` — LLM extraction with contamination test. Built, never run.
- `src/edgar.py` — 33.9M XBRL facts, point-in-time resolver, TTM assembly, tag fallback chains.
- `src/filings.py` — 65,549 filings indexed with acceptance timestamps.
- `src/insider.py` — 480,796 Form 4 transactions.
- `src/backup.py` — verified `VACUUM INTO` backup. **The 14.1 GB DB is partially irreplaceable
  (`fetch_period=2y`) and has never been backed up to external media. Nag the owner about this.**

---

## Operational state as of 2026-09-16

- **303 tests green.** `pytest tests/ -q`
- Live model: `v0.5_expanded_universe`, 1,521 names, nightly via Task Scheduler.
- Git: `github.com/evanaz32006/market-warhorse` (private), branch `main`, clean.
- **Task Scheduler still kills the run on battery** (`StopIfGoingOnBatteries=True`). Four sessions
  lost to this. Needs an elevated PowerShell — the owner has the command.
- Secrets in `.env` (gitignored); `SEC_CONTACT_EMAIL` required or EDGAR blocks you.
- Deadline: the owner's Claude credits expire **2026-09-19**. Claude.ai credits do NOT fund the
  Anthropic API — separate billing.

---

## Suggested order

1. **Fix #1 (live/backfill divergence).** Nothing else is trustworthy until the thing being
   measured is the thing that runs. ~half a day.
2. **Measure #2 (survivorship).** Settles whether there is any real edge at all. ~1 day.
3. **Start accumulating estimate revisions and options data nightly.** Costs nothing, and in six
   months there is a history that cannot be bought retroactively for free. Do this on day one so
   the clock starts.
4. **Run the filing-text pilot** if the owner funds a key.
5. **FRED macro regime features** — backfillable, decades deep, aimed at the timing gap.

The owner is sharp, reads the numbers carefully, and has personally caught several real bugs by
noticing arithmetic that did not add up. Show your working, give him the honest number, and do not
soften a bad result — he handles those better than he handles hedging.
