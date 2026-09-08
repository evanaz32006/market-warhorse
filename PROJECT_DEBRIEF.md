# market-warhorse — project debrief

*Context document for an AI assistant helping draft a scholarship application. Written 2026-09-08.*
*Everything below is verified against the live codebase and database — no estimates, no rounding up.*

---

## TL;DR for whoever is drafting

A high-school student built, alone, a **1.35-million-row quantitative equity research system** that
ingests SEC filings and market data, ranks ~1,500 US stocks daily, and — this is the unusual part —
is engineered specifically **to catch itself producing false results.** Over the build it repeatedly
did exactly that, and the owner acted on the bad news rather than burying it.

**The strongest angle for an application is not "he built a trading bot that makes money."**
It doesn't, and the system's own measurements say so. The angle is: *he built the measuring
instrument, held it to a standard most professionals skip, and let it tell him he was wrong.*
That is a rarer and more defensible story than a performance claim, and it cannot be faked by
someone who has only followed a tutorial.

---

## What it is, in one paragraph

`market-warhorse` is a stats-only research and ranking system for swing trading. Every trading day it
pulls prices for ~1,500 US companies, reconstructs each company's fundamentals **as they were known on
that date** from raw SEC EDGAR filings, computes ~60 features per stock, ranks the whole universe
within GICS sectors, produces composite scores at four holding horizons, and then — weeks or months
later — grades its own past predictions against what actually happened. It places no trades and
connects to no broker by design.

---

## Verified scale

| | |
|---|---|
| Source code | **11,027 lines** across 15 modules and 16 test files |
| Automated tests | **204**, all passing |
| Database | **14.1 GB** SQLite |
| Price history | **797,134** daily bars across **1,527** tickers |
| SEC XBRL facts ingested | **33,921,816** across **1,502** companies |
| Scored snapshots | **1,353,875** rows, 124 columns each |
| Coverage | 2024-06-24 → 2026-09-04 (~2.2 years) |
| Model versions | **5**, run side-by-side, all immutable |
| Universe | S&P 500 + S&P 400 midcap + S&P 600 smallcap |

Runs unattended nightly via Windows Task Scheduler, with self-healing recovery that detects and
reconstructs any trading day the machine missed.

---

## Why this is technically hard (the part worth explaining to a reviewer)

### 1. Lookahead bias — the failure mode that makes a system lie beautifully

The central hazard in quantitative finance is accidentally using information from the future. A
system that does this produces a backtest that looks spectacular and is completely worthless. It is
easy to do by accident and nearly invisible once done.

The whole architecture is organized around preventing it:

- Forward returns are joined by **real trading date within each ticker's own price series** — never by
  row position across a mixed table, which is the classic silent bug.
- Fundamentals come from EDGAR gated on **`filed_date <= D`**: a company's Q2 numbers only become
  visible to the model on the day they were actually filed with the SEC, not on the day the quarter
  ended. That distinction is roughly five weeks of foresight per quarter.
- When a company later *restates* a figure, the **originally-filed value wins** — because the restated
  number did not exist when the market reacted.
- The backtest fills orders at the **next session's open**, never at the closing price used to make
  the decision. There is an automated test that constructs a 2× gap between those two prices, so a
  wrong implementation is caught by the share count rather than by inspection.

### 2. Point-in-time fundamentals from raw filings

Free data sources (Yahoo Finance) only give *today's* fundamentals — no history. That made
value/quality factors untestable. The fix was to ingest **33.9 million raw XBRL facts** directly from
SEC EDGAR and reconstruct, for any date in history, exactly what had been publicly filed by then.

This required solving real accounting problems, not just plumbing:
- **Trailing-twelve-month assembly** for US filers, who file only three 10-Qs a year (Q4 never exists
  as a standalone filing), across non-calendar fiscal years.
- **Tag fallback chains** — companies tag the same concept differently, and *change* tags over time.
- **Sector-specific exclusions** — banks and REITs don't report comparable operating margins, so those
  fields sit out rather than being faked.

### 3. Statistical honesty about small samples

Two years of daily data looks like ~500 observations. At a 120-day holding horizon it is really about
**3 independent observations**, because overlapping windows share almost all their data. The system
computes overlap-adjusted t-statistics everywhere and reports the effective independent sample size
next to every conclusion, so a result computed on 3 observations can never be read as settled.

---

## The engineering discipline: pre-registered validation gates

Before trusting EDGAR-derived fundamentals, a **pass/fail bar was written down in advance** — median
error < 10%, rank correlation > 0.90, fewer than 5% of companies off by >100% — and the pipeline was
required to clear it against an independent source before any historical data was generated.

**The gate caught six real bugs.** Three would have silently corrupted years of data with numbers that
looked entirely reasonable:

1. **Abandoned XBRL tags.** NVIDIA stopped using one revenue tag in 2022 but the old facts remain in
   EDGAR forever. The resolver was taking the first tag that returned anything, so it silently paired
   2022 revenue with 2026 operating income and produced a **603% operating margin**. 40 of 360
   companies had the same pattern.
2. **Negative-equity rank inversion.** Debt-to-equity is scored "lower is better." Companies with
   negative book equity (Clorox, DaVita) produced values near **−3,700**, which would have ranked *the
   most leveraged company in the index as its safest holding.*
3. **Missing lease obligations.** Debt excluded lease liabilities, understating leverage by a
   systematic 6–9% that *worsened as companies got smaller* (small caps lease more of what they use).
   Fixing it moved the error from 8.2/9.1/10.5% to 3.9/2.8/2.1% across large/mid/small — and small
   caps went from the *worst*-matching bucket to the *best*, which is what a real fix looks like as
   opposed to tuning a number until it passes.

Plus: wrong debt concept and units, REIT revenue read from the wrong accounting tag (a 160× error),
and profit margins built from two different fiscal periods.

**None of these would have thrown an error.** All of them produce plausible, confident, wrong numbers.
That is the entire argument for the gate.

---

## What the system actually found (including the parts that don't flatter it)

### It works where theory says it should
On a two-year backtest, the top-ranked bucket returned **+10.2%** excess over 120 days versus **−1.9%**
for the bottom bucket, with hit rates of 53% vs 41%. Component predictive power *grows with horizon*
exactly as published research predicts (trend signal: 0.01 → 0.12 from 5 to 120 days). That pattern is
used as a **correctness test**, not a victory lap: if short-horizon signals had dominated instead, the
documented response is to suspect a bug before believing the result.

### Four hypotheses tested and killed
- **Post-earnings drift (SUE)** — computed standardized earnings surprise from raw filings. No
  detectable signal. All t-statistics below 1.2.
- **Short-term reversal** — real but too weak to trade after spreads.
- **Earnings-timing effects** — nothing significant.
- **"Look where fewer people are watching"** — expanded the universe 3× into mid- and small-caps on
  the theory that short-horizon inefficiency survives in less-watched names. Found a faint ordering in
  the predicted direction (small > mid > large) but **every t-statistic below 1.0**. Closed off.

### The portfolio simulation says: smoother, not better
Simulating an actual account with realistic spread and market-impact costs across nine
configurations: **eight of nine lost to simply buying and holding SPY** on total return (SPY did 18.4%
annualized). The strategy won on *risk-adjusted* terms — Sharpe 1.53 vs 1.10, max drawdown −6.7% —
but that is a different and weaker claim than beating the index.

Every output row is stamped **`survivorship_biased=True`** with the direction of the bias, because the
universe is today's index membership projected backwards and delisted companies are absent.

### Machine learning lost to hand-set weights
Four automated weight-fitting methods (IC-weighted, IC-ratio, ridge regression, non-negative least
squares) were tested strictly out-of-sample against a **pre-registered** success criterion. **Zero
passed.** Ridge was the instructive near-miss: it beat the baseline on one metric and lost on the
other. Had the criterion been written loosely enough to accept it, the weights would have been
changed on what is almost certainly noise.

---

## The thing worth emphasizing

Across roughly a dozen distinct bugs found during this build, **almost none produced an error
message.** They produced confident, plausible, wrong output — an empty result that read as a finding,
a chart labeled "live data" that was computing something else, a baseline that was silently absent so
every alternative "won" by default.

The system's response was structural rather than vigilant: hard failures replacing silent empties,
assertions at the point of change, and tests written as adversarial claims ("a fill at yesterday's
close *must be rejected*") rather than as coverage. That instinct — *assume the tool is lying and
build the thing that would catch it* — is the transferable skill here, and it applies well beyond
finance.

---

## Honest limitations (do not let the application overstate these)

- **It is not profitable, and does not claim to be.** It loses to a passive index fund on returns.
- **The edge sits where the data is thinnest.** ~3–7 independent observations at the horizons that
  matter.
- **Survivorship bias inflates every historical number**, and it is worse for small caps.
- **The live out-of-sample record is short** — the current model version has weeks, not years.
- **One data field remains unverified** (`operating_margin`) and is deliberately withheld from scoring
  rather than used on an assumption.

An application that claims market-beating returns would be **contradicted by the project's own
output files** — which is exactly the trap this system was built to avoid. The credible claim is
methodological rigor, not performance.

---

## Suggested framing angles

1. **Built the instrument, not just the idea.** Most people testing a market theory build something
   that confirms it. This is infrastructure built to *falsify* — and it did, four times.
2. **Professional-grade discipline, self-taught.** Pre-registered hypotheses, immutable versioned
   experiments, point-in-time data reconstruction, overlap-adjusted statistics. These are practices
   from institutional quantitative research, arrived at independently.
3. **Comfort with negative results.** Four killed hypotheses, a strategy that loses to the index, and
   machine learning that failed to beat hand-set weights — all reported plainly, in writing, in the
   project's own documentation.
4. **Real scale, real constraints.** 14 GB of data, SEC rate limits, a 26-hour job optimized to 15
   minutes, crash-resumable multi-hour pipelines — engineering problems solved because they blocked
   the research.
5. **Entrepreneurial shape.** Self-directed with no assignment or grade attached; scoped, planned, and
   revised across five versioned iterations, each isolating one variable so results stayed
   interpretable.

---

## If the drafting assistant needs specifics

The repository contains `SESSION_STATE.md` (detailed engineering log with every bug and its
reasoning), `ROADMAP.md` (decisions and standing disciplines), `CLAUDE.md` (the invariants the system
is built around), and `output/DAILY_LOG.md` (the machine-generated daily audit trail). Results live in
`output/research/` as CSVs. The code is version-controlled with a clean commit history.
