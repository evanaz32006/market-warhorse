# NEXT STEPS — the bulk-work phase (written 2026-09-09)

**Working deadline: 2026-09-19** (Claude credits). Goal is not refinement — it is adding whole new
CLASSES of data and features. Trade placement is explicitly deferred.

**Standing instruction from the owner:** work autonomously. Review the data and the program, plan the
next step, execute, report. Do not wait for approval on ordinary work; stop only at genuine forks.

---

## The strategic read

Everything measured so far says the price/volume + fundamentals feature set is **exhausted at short
horizons**. The 5–40d band is empty across large, mid AND small caps; SUE, reversal and earnings
timing all failed. Signal exists only at 60–120d and comes from momentum/trend/value.

CLAUDE.md already predicted this: *"The edge comes from richer DATA added later, not from these
price/volume stats."* So the remaining work is genuinely **new inputs**, not tuning.

### The force multiplier to build FIRST

Do not hand-code one feature per idea. Build a **conditional-pattern test harness** that answers
"after condition X, does Y happen?" as a query rather than a build. The owner has many such
hypotheses ("strong tech week → weak Friday"). One harness turns each from a day of work into
minutes, and lets dozens be screened before any becomes a feature.

Requirements: point-in-time by construction, cross-sectional or index-level, reports hit rate +
effect size + overlap-adjusted t + effective independent sample size, and **screens for
multiple-comparisons risk** (testing 200 patterns will produce ~10 "significant" ones by chance —
this must be stated in the output, not left to the reader).

---

## Tier 1 — free, backfillable, NO new infrastructure. Start here.

### 1a. Calendar & conditional seasonality (the owner's own hypothesis)
100% computable from `price_history`, which already holds 798k bars. Zero new dependencies.
- Day-of-week, turn-of-month, month-of-year, pre/post-holiday, quarter-end, triple-witching.
- **Conditional patterns**, which is the real target: "after a top-decile week for a sector, does that
  sector underperform the following Friday?" "After N consecutive up days, what happens?"
- Test at the SECTOR level (sector ETFs are already in the DB) and at the index level.
- Caveat to enforce: seasonality is the single most data-mined area in finance. Anything found here
  needs the multiple-comparisons screen and an out-of-sample split before it is believed.

### 1b. SEC Form 4 — insider transactions
**Free, and the EDGAR ingest pipeline already exists.** Form 4 filings carry exact filed timestamps,
so they are point-in-time perfect — the same `filed_date <= D` gate already used for fundamentals.
Insider buying is one of the better-documented free anomalies. Already named in ROADMAP as a
wide-pipe future factor. Highest value-to-effort of anything on this list.

### 1c. SEC 8-K — material event flags
Also free, also already-built infrastructure. 8-Ks are the "something happened" disclosures with exact
timestamps. Even a simple `days_since_8k` / `8k_in_last_5d` flag is a genuinely new information class,
and unlike news sentiment it is unambiguous and perfectly dated.

### 1d. Market breadth & regime state
The existing `market_regime_component` is thin (one benchmark's SMA position). Compute real breadth
from the 1,527-name universe already in the DB: % above SMA200, advance/decline, cross-sectional
return dispersion, new-high/new-low. Free via `^VIX` on yfinance for volatility regime.

---

## Tier 2 — free, but needs a new pipeline

- **FINRA short interest history.** Currently short interest is yfinance live-only and never
  backfills (it is null on all 779k backfilled rows — this is why `short_interest_component`
  contributes nothing). FINRA publishes free bi-monthly history. Would make the factor testable.
- **GDELT** — free, global news volume/tone, timestamped, backfillable via API. The credible
  "alternative data" option.
- **FOMC / economic calendar** — free, deterministic dates, trivially point-in-time.

---

## Tier 3 — the social/political data idea: honest assessment

The owner specifically wants Trump/Twitter-style posts. Reality check before spending days on it:

- **Truth Social has no free stable API.** X/Twitter API is paid and expensive.
- Historical archives exist but **timestamp precision is the whole game** — a post's market impact
  lives in minutes, and this system operates on daily bars. A daily-resolution feature built from
  intraday-sensitive events will mostly measure noise.
- Reproducibility is poor: archives get deleted, rate-limited, or change format.

**Recommendation: do NOT start here.** Not because the idea is bad — political/news shocks obviously
move markets — but because it is the *worst* value-to-effort item on this list while 1b and 1c are
free, perfectly dated, and use infrastructure that already exists. If sentiment is still wanted after
Tier 1, GDELT is the defensible entry point.

---

## Execution order

1. ~~**Build the conditional-pattern harness**~~ — **DONE 2026-09-09**, `src/patterns.py`,
   `--research patterns`. 18 tests.
2. ~~**Run the owner's own hypotheses through it**~~ — **DONE.** 198 tests across 6 families.
   8 nominally significant, 9.6 expected by chance, **zero surviving correction**. Friday is the
   STRONGEST weekday for SPY, not the weakest (t = 1.42, n.s.). Full detail in SESSION_STATE.
3. ~~**Form 4 ingest**~~ — **DONE 2026-09-10**, `src/insider.py`, `--ingest-insider`,
   `--research insider`. 480,796 rows, 1,483 of 1,509 names, filed 2024-01-02 .. 2026-03-31.
4. **8-K event flags** — same EDGAR pipeline, next up.
5. **Breadth/regime features.**
6. Re-evaluate. Tier 2 only if time remains.

### Carried forward from the Form 4 work

- **Insider coverage ends 2026-03-31** while prices run to 2026-09-08, because SEC publishes the
  quarterly datasets on a lag (2026Q2/Q3 return 404). Reads past that date return `None` with
  `coverage_missing=True`, never 0. **A live path would be needed before this could ever become a
  scored feature** — the bulk datasets alone cannot serve a nightly run. That work is deliberately
  NOT done yet: measure first, deploy later. If the signal is not there, the live path is days
  spent wiring up a dead factor.
- **`--research patterns` and `--research insider` are report-only** and read no `model_version`
  state, so neither needs re-running when a version is promoted.

Each new factor follows the established discipline: new feature column → new `model_version` →
pre-registered validation gate → backfill → IC measured against priors. **One variable at a time.**

---

## Survivability (must happen before 2026-09-19 regardless)

After the deadline the owner operates this alone.

- ~~**`data/market_data.db` backup script**~~ — **DONE 2026-09-10**, `src/backup.py`,
  `python app.py --backup <DEST_DIR>`. Uses `VACUUM INTO` (a plain file copy in WAL mode silently
  loses uncheckpointed writes), then reopens the result, runs `PRAGMA integrity_check`, and matches
  row counts against the source — raising on failure rather than reporting it in a field nobody
  reads. **Still needs to actually be RUN, to a different physical device.** The file is 14.1 GB and
  partially irreplaceable: `fetch_period` is 2y, so bars older than the rolling two-year window
  exist in exactly one place.
- Code is now in git (local, no remote). A remote would need the owner's explicit go-ahead.
- A short "operate this alone" doc: what to run, what breaks, how to read the daily log.

---

## Known open items carried forward

- **`operating_margin` still withheld** from scoring. EDGAR runs a uniform ~0.81× yfinance across
  unrelated sectors — a constant that consistent points to a definitional difference in the operating
  income numerator, not company-specific noise. Audit list with tags and periods is in
  `output/operating_margin_audit.csv`; MDT is the cleanest name to check against a 10-K.
- **Nightly evaluation takes 266s** (779k rows re-evaluated nightly, 542 of those dates immutable).
  Owner decided to skip the caching fix — silent-staleness risk around splits was not worth ~2 min.
- **`short_interest_component` is dead weight** — null on every backfilled row. Either fix via FINRA
  (Tier 2) or drop it from the weights.
- **Section 3 "Live" columns read n/a** post-promotion — correct behavior, will fill as v0.5 live
  dates accrue (13 as of 2026-09-08).

---

## State as of 2026-09-09

- **v0.5_expanded_universe** live since 2026-08-21; 13 live dates, 1,527 names.
- 204 tests passing. Nightly run healthy and unattended.
- 5 model versions, all immutable, side-by-side.
- 1.35M scored snapshots · 33.9M EDGAR facts · 798k price bars · 14.1 GB.
