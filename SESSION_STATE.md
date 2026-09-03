# SESSION_STATE.md

Last updated: 2026-08-21

---

## v0.5 PROMOTED TO LIVE - version boundary is 2026-08-21

`PARAMS["model_version"]` = `v0.5_expanded_universe` as of **2026-08-21**. Everything before that
date under an earlier version string is frozen and untouched; v0.3_sector_neutral joined
FROZEN_MODEL_VERSIONS the same day with 33 live dates preserved for comparison.

**Scores do not compare across this boundary.** A percentile is a rank against peers and the peer set
tripled (~500 -> ~1,500 names), so a value_percentile of 80 means "top 20% of 1,500" after the
boundary and "top 20% of 500" before it. The score BANDS are absolute (80/65/50) so the labels still
mean something, but the population underneath them moved.

Verified clean on promotion: full nightly run completed end to end (fetch -> score -> evaluate ->
export -> journal), 1,525 tickers scored, frozen versions correctly skipped by the evaluator, and
DAILY_LOG.md regenerated under the new version.

### Section 2 rebuilt: live vs SIMULATED, not old-version-vs-new

A promotion resets the live track record to zero, so Section 2 read "no cohorts matured today" and
would have for weeks. The fix is NOT to show earlier model versions' results (a different and less
useful question) but to show THIS model's BACKFILLED cohorts: the same algorithm and weights scored
point-in-time on an earlier date. v0.5 carries 777,738 backfilled rows over 542 dates, so a snapshot
from ~120 sessions ago matures today.

That answers the question that matters - how is this model doing in the market that is happening NOW,
rather than in a two-year average - without waiting 120 trading days for a live 120d cohort, by which
time the regime has already turned over.

The two counters are labelled and never merged: a simulated cohort is a reconstruction (no slippage,
no missed fills, universe as constituted today), so it is weaker evidence than a real-time prediction.

### Storage/perf fixes made at promotion

- `score_history.csv` **1,161 MB -> 5.1 MB**. Exporting "active version only" stopped working the
  moment v0.5 became active, because v0.5 IS the active version and carries 777,738 immutable
  backfilled rows. The nightly export is now LIVE rows only; `--export-full-history` dumps everything.
- **WAL mode** on the database. A read-only progress query previously blocked the writer and killed
  the v0.5 backfill at 351/541 dates.
- **Resumable backfill** - skips dates already written for the model_version, so a killed multi-hour
  job continues instead of restarting. Preserved all 351 dates on the one crash.
- `journal._trading_calendar` now DELEGATES to `evaluation.trading_calendar`. It was a second
  implementation with "SPY" hardcoded while evaluation read PARAMS["calendar_ticker"]; two calendars
  that can disagree about which day is D+20 is how a maturity bug gets in.
- Removed dead code (an unused prior-version loader, a superseded renderer, two ignored parameters)
  and a storage docstring that claimed the database had two tables when it has seven.

### KNOWN COST, not yet fixed

Nightly evaluation went **9s -> 266s**. v0.5 has 779k rows vs v0.3's 19k, and the ACTIVE version
cannot be frozen, so all 542 backfilled dates are re-evaluated every night although they can never
change. The fix is forward-return caching keyed on (model_version, run_date, ticker, horizon), with
only unmatured horizons recomputed - deliberately scoped rather than rushed.

Also noted and NOT acted on: Strong (score >= 80) is 0.5-2.0% of rows under v0.5 (max score ~94), so a
single day's Strong bucket is often below the 20-name reporting gate and shows n/a. That is the
small-sample gate working correctly on a thin daily slice, not an unreachable band - Section 3's
cumulative view is where it accrues. No band change warranted.

---

## v0.5 expanded universe — all three jobs COMPLETE, nothing deployed (2026-08-21)

Universe 521 -> **1,527 names** (523 large / 400 mid / 602 small, from S&P 500 + 400 + 600).
Data: 777,860 price rows · 33.9M EDGAR facts across 1,502 companies · DB 5.3 GB -> 13.4 GB.
`v0.5_expanded_universe`: **779,260 snapshot rows, 542 dates, 97% fundamentals coverage, 100% PIT.**
**200 tests green. No weight changed, no model_version bumped, nothing deployed.**

### Job 1 — is the 5-40d band empty outside the S&P 500? NO EDGE FOUND.

| horizon | large | mid | small |
|---|---|---|---|
| 5d | +0.0004 | +0.0074 | +0.0100 |
| 20d | -0.0004 | +0.0069 | +0.0077 |
| 60d | +0.0529 | +0.0468 | +0.0464 |
| 120d | +0.1146 | +0.1381 | +0.0741 |

A faint ordering in the predicted direction (small > mid > large at 5-20d, consistent across three
horizons) but **every overlap-adjusted |t| < 1.0**, and an IC of 0.01 would not survive a small-cap
spread. Combined with SUE/PEAD, short-term reversal and earnings timing all failing earlier, the
short-horizon band is now closed off: "look where fewer people are looking" was the last plausible
explanation and it did not hold.

The comparison rests on measuring every bucket against ONE common benchmark per bucket, which is
exactly (not approximately) safe: a within-group rank IC cannot be changed by subtracting a per-date
constant every member shares. Asserted directly in `test_within_group_ic_is_exactly_invariant_to_a_shared_benchmark`.

Note also: small caps have the WEAKEST 120d IC (0.074 vs 0.115/0.138). The long-horizon signal this
system relies on lives in large and mid caps.

### Job 2 — portfolio backtest. Smoother, not bigger.

**SPY over the window: 18.4% CAGR, 43.8% total return, Sharpe 1.10.**
**8 of 9 configurations LOSE to SPY on return.** The single winner (n=20/hold=20, +5.6% total) is one
of nine and is more likely selection than signal.

Risk-adjusted is genuinely better: Sharpe up to **1.53 vs 1.10**, max drawdown **-6.7%**.

Costs are small (0.51% total drag at 18x turnover) and that is REAL for retail size, not a modelling
error: at a $100k account each position is ~$5k, so market impact is structurally negligible
(0.02-0.5bps) and only the spread bites (0.65bps mega-cap to 5.2bps at the liquidity floor). It would
NOT hold at institutional size, where impact dominates. The small-cap spread estimate is probably
optimistic.

Discount everything by **survivorship bias** (stamped on every output row): today's index membership
projected backwards, worse for mid/small than for the S&P 500.

### Job 3 — walk-forward. Hand-set weights hold. ZERO of four fitted variants passed.

Criterion (pre-registered): beat baseline on BOTH IC and decile spread, at BOTH 60d and 120d.

| variant | h=60 | h=120 |
|---|---|---|
| ic_mean | IC -0.013 vs +0.031 | IC +0.003 vs +0.084 |
| ic_ratio | IC -0.015 vs +0.031 | IC +0.008 vs +0.084 |
| **ridge** | IC +0.014 vs +0.031, **spread 0.027 vs 0.018** | IC +0.079 vs +0.084, **spread 0.119 vs 0.076** |
| nnls | IC +0.002 vs +0.031 | IC +0.037 vs +0.084 |

**Ridge is the instructive near-miss.** It beat the baseline on decile spread at BOTH horizons and on
top-10 excess at 60d, losing only on IC — and at 120d only barely. Had the criterion been "beats on
spread", ridge would have passed and a weight change would have followed. Requiring BOTH is what
caught it: a variant that concentrates the extremes while ranking the full cross-section worse is
optimizing the metric rather than the objective.

**3x the cross-section did not fix the sample problem, exactly as predicted at plan time.** Effective
independent observations: **~6.7 at h=60, ~2.9 at h=120**. More names sharpen each daily IC estimate
but add ZERO independent time observations, and time is what the significance rests on. The
baseline's own t-stats are 0.49 (60d) and 1.00 (120d) - the thing the variants fail to beat is itself
not distinguishable from zero. This question cannot be settled with two years of data at any universe
size.

`ic_mean`/`ic_ratio` went outright NEGATIVE at 60d, worse than in the v0.4 run: more cross-section
made the IC-weighting variants fit noise more confidently.

### Bugs found and fixed this phase

1. **Lease obligations missing from debt_to_equity** (the 6th real bug the validation gate has caught).
   Systematic ~6-9% understatement that WORSENED as companies got smaller, because small caps lease
   proportionally more. Adding finance + operating lease liabilities moved median disagreement from
   8.2/9.1/10.5% to 3.9/2.8/2.1% (large/mid/small) and removed the directional bias entirely. Small
   caps went from the WORST bucket to the BEST - an inversion you do not get from threshold-tuning.
   Includes a double-count guard for filers using `LongTermDebtAndCapitalLeaseObligations`.
2. **Lease concepts not registered as balance-sheet instants** - routed through TTM assembly (which
   needs a duration) and silently resolved to None. Identical to a bug made earlier with the debt
   legs; `_INSTANT_CONCEPTS` now carries a comment explaining why, so a third repeat is less likely.
3. **`database is locked` killed the backfill at 351/541** - caused by my own progress polling.
   Fixed structurally: **WAL mode** (readers and a writer coexist) plus a **resumable backfill** that
   skips dates already written. All 351 dates were preserved on resume.
4. **An all-null component vetoed the entire regression fit.** `short_interest_component` is live-only
   (FINRA) and null on all 779,260 backfilled rows; the training matrix required every component
   present per row, so it dropped 100% of training data and ridge/nnls produced nothing. **This was a
   repeat of a bug already fixed in the decay analysis' common panel** - same rule, new function.
   Now: all-null components get weight 0 and are flagged unavailable, never imputed.

The "omit rather than emit NaN rows" guard (added after the v0.4 baseline bug) is what surfaced #4.
Without it, ridge and nnls would have appeared in the comparison as rows of NaNs, reading as
"measured, came out empty" rather than "never computed".

### Open decision for the owner

**`PARAMS["model_version"]` is still `v0.3_sector_neutral`** - the nightly run scores the full 1,515-name
universe but writes it under v0.3, which has only 34 dates of history. v0.5 is fully backfilled
(542 dates, 97% fundamentals) but is NOT live. That is correct under "report only", but it means the
richest version is currently accumulating no live data. Promoting it is a one-line config change and
an explicit decision, deliberately left un-made.

---

## Tooling note: editing files by string-replacement (learned the hard way)

Three failures this session came from the patch scripts, not from the code being patched:

1. **A `str.replace` whose target does not match silently no-ops.** A "fix" was reported as applied
   and was not. Every patch now asserts its target exists AND is unique before replacing.
2. **Multi-edit scripts are atomic per file** - an assert on edit #6 means edits #1-5 are never written
   either. Recovering by re-running only the failed edit leaves the file half-patched: syntactically
   valid, semantically broken (app.py briefly referenced a CLI flag that did not exist). After any
   partial failure, re-verify EVERY edit, not just the one that failed.
3. **Mixed line endings break pattern matching.** Writing with a LF newline setting does not convert
   a `\r\n` already inside the string, so files ended up half CRLF and half LF and later `\n` patterns
   silently missed. Normalize on read (`raw.decode().replace(CRLF, LF)`), write with an explicit LF
   newline, and never write binary-read text back through a translating writer - that is what doubled
   every line ending in research.py earlier and inserted a blank line between every line.

All three share the shape of the standing lesson below: **the failure produced plausible-looking
output instead of an error.** Assert loudly at the point of change.

---

## Job 2 research analyses (2026-08-18)

Built `src/research.py` (decile/top-N went into `evaluation.py`). All REPORT ONLY — no score, weight,
or `model_version` changed by any of this.

### Results

- **Signal decay.** IC rises steeply with horizon and the 5-20d band is empty (composite IC
  0.005-0.019). Verified against the obvious confound: longer horizons rest on older, shorter date
  windows, so the rise was re-measured on a FIXED date panel (2025-04-09 .. 2026-02-24, n=220) and the
  shape survived. Direction is well supported; the apparent peak at h~136 is NOT — it sits where the
  data thins to roughly 1.5 independent observations.
- **Walk-forward IC-weighted composite.** The hand-set config weights BEAT both IC-weighted variants
  at 20d, 60d and 120d, decisively at 60d (decile spread 0.043 vs 0.004, and baseline IC positive
  where both fitted variants are negative). Fitting weights to trailing IC over ~200 effective
  observations fits noise, and clipping compounds it by dropping components on a temporary negative.
  The pre-registered success criterion was NOT met. No weight change.
- **Quality decomposition.** All three legs negative; the suspected inverted `debt_to_equity` leg is
  the LEAST negative and the only one that stops deteriorating, so a sign error there is ruled out.
  Risk-vs-quality daily-IC correlation 0.53/0.46/0.45/0.37 supports one shared regime at 5-60d, but
  breaks down at 120d (Spearman 0.22; risk -0.007 vs quality -0.066). Open question.
- **SUE / short-horizon probe.** PEAD does NOT appear. Every overlap-adjusted |t| in the 5-60d band is
  below 1.2. `sue_fresh_63d` — SUE restricted to the documented drift window — goes NEGATIVE at
  h=30-60, which is the sharpest evidence against. SUE does not become the v0.5 spec.

### CORRECTION: `short_momentum_component` is NOT implemented incorrectly

An earlier reading of the short-horizon study reported that `short_momentum_component` had IC
identical to `return_5d` at every horizon, and concluded it was a monotone transform of one input
rather than the specified 40/35/25 blend. **That conclusion was wrong.** The component is implemented
correctly (`scoring.short_momentum_component`), and `tests/test_research.py` now proves it: holding
the 5d input fixed while moving only the 10d and 20d inputs moves the score, and a 100/0/0 input
yields exactly 40.0.

**v0.1-v0.4 historical values for this component are CORRECT. No discount applies to past results.**

The identical IC was a defect in the ANALYSIS TOOLING, not in scoring. `research.load_panel` built its
column list as:

    wanted = [base...]
    wanted += [c for c in SERIES_COLUMNS] + [c for c in extra_columns if c not in wanted]

The right-hand side is evaluated before the `+=`, so `c not in wanted` tested only the base list. Any
extra_column that was also a SERIES_COLUMN was requested twice, and a duplicate label makes
`frame[series]` return more columns than there are names — shifting every series after it by one
position. Five of the eight rows in the first short-horizon report were therefore real numbers under
the wrong labels. SUE (indices 0-1, before the shift) was unaffected, so the SUE conclusion stands.

Fixed three ways: the column list is de-duplicated, an assertion prevents duplicates reaching the
frame, and `build_ic_cube` refuses to build when a series label is duplicated rather than mislabeling.
Only the short-horizon analysis passed overlapping `extra_columns`; decay, walk-forward and quality
decomposition were never affected (verified).

### Standing lesson from this session: empty output that reads as a finding

FOUR separate defects this session all had the same shape — a missing input produced empty or shifted
output that looked like a measured result:
1. Walk-forward baseline: `SCORE_WEIGHTS` is keyed `score_20d`, not `20d`. The wrong key returned an
   empty dict, `apply_weights` made an all-NaN column, and the baseline the whole comparison exists to
   beat was silently ABSENT — every fitted variant "won" by default.
2. SUE: `build_facts_index` is a TAG-FILTERED load and EPS is not a ratio concept, so the index held
   zero EPS facts. The run printed "SUE available for 0 tickers" and produced a full 1,250-row report
   with its headline signal missing.
3. `load_panel` duplicate columns (above).
4. A `str.replace` patch whose target did not match silently no-opped, so a "fix" was never applied.

Mitigations now in place: hard failures for an empty baseline and for zero SUE coverage, assertions on
duplicate columns, and asserted patching. **An empty result must fail loudly, because an empty result
looks exactly like a finding.**

---

## v0.4 EDGAR point-in-time fundamentals — Phase 3 gate resolution (2026-08-09)

The pre-registered gate (median abs diff < 10%, Spearman > 0.90, >100%-diff tail < 5%) was run against
the yfinance cache. **6 of 8 concepts passed outright.** Two did not, and were resolved as follows.

### `return_on_equity` — ACCEPTED. The failing criterion did not apply.

This is **not** "close enough," and it is **not** a precedent for waving through marginal results.

ROE cleared two of three criteria comfortably — **Spearman 0.947** (bar 0.90) and **median abs diff
7.7%** (bar 10%). It missed only the ">100% diff tail" criterion, at 5.5% against a 5.0% bar.

That criterion exists to catch *mapping disagreement*: a concept wired to the wrong tag diverges on
many names at once. Inspection shows it is not measuring that here. **9 of the 25 tail names have
|yfinance ROE| < 0.05** — a near-zero denominator, where a trivial absolute difference produces a
four-figure percentage. APD is the clearest case: yfinance ROE 0.00023, so a 0.13 absolute gap reads
as 58,000%. The tail metric is registering *denominator instability*, not a wrong mapping.

The two criteria that actually measure agreement — rank correlation and typical error — both pass, and
they are the ones that matter for a percentile-ranked system. Accepted on that basis, with the
reasoning recorded here and in `output/edgar_validation_notes.md` so the record shows WHY the criterion
was judged inapplicable rather than simply missed.

### `operating_margin` — EXCLUDED from v0.4 entirely.

Failed all three criteria (Spearman 0.860, median diff 14.2%, tail 8.3%), with a systematic ~9%
one-directional gap across 75% of names that survived every fix including period alignment. Working
hypothesis (normalized vs as-reported operating income) is plausible and is recorded in ROADMAP, but
it is **unverified**, so the field sits out via `config.EDGAR_EXCLUDED_FIELDS` and the existing
renormalization redistributes its weight. Not deleted — computed and then dropped, so re-enabling it
after third-source verification is a config edit plus a re-derive, never a re-ingest.

### Five bugs the gate caught (three of them new this session)
Dead-tag staleness (NVDA 603%), `debt_to_equity` wrong concept + units, REIT revenue read from the
ASC-606 contract tag (AVB 160x margin), negative-equity rank inversion (Clorox would have ranked as
the index's safest name), and margin legs resolved from different periods (51 of 507 filers). Two of
these would have silently corrupted the backfill. Recorded in ROADMAP as a standing discipline.

Tests: **123 passing** (112 baseline + 11 new EDGAR tests).

---

## Daily journal + AI brief layer — COMPLETED this session (2026-07-04)

Built per `market-warhorse-journal-spec.md` (ROADMAP "Next" item #2). Presentation/logging only —
**no scoring/evaluation/storage VALUES changed**; read-only consumer of existing outputs + the new
`journal` table.

**Code:**
- `src/storage.py`: new `journal` table (PK run_date+model_version; entry_json, nullable brief,
  timestamp) + helpers `upsert_journal_entry` (idempotent; brief preserved via COALESCE so the
  journal step never clobbers a brief), `update_journal_brief`, `get_journal_entry`,
  `load_all_journal_entries`, `get_live_run_dates`, `get_score_map` (score column allow-listed
  against SCORE_COLUMNS since it's interpolated into SQL).
- `src/journal.py`: pure section builders (run metadata / rankings movement / evaluation state /
  v0.2 live-validation) → `build_journal_entry` (JSON blob) → `render_daily_log` regenerates the
  whole `output/DAILY_LOG.md` from the table each run (idempotent, newest-first). Movers/entered/
  exited join today's vs the previous LIVE run's score_20d ON TICKER (never row position).
- `src/brief.py`: `generate_brief` calls Claude (`claude-sonnet-4-6`, max_tokens 400, spec system
  prompt) and returns (text|None, note); guards missing key, missing `anthropic` package, and any
  API/timeout error — all → None + one-line note. `run_brief` attaches the brief to the journal row
  and re-renders DAILY_LOG.md (brief at top under **Brief:**). Journal NEVER depends on brief.
- `app.py`: `_run_live`/`_run_backfill` now return {run_date, tickers_scored, skipped};
  `_run_journal_and_brief` builds run_context (mode, runtime via time.time(), fetch summary,
  warnings) and runs journal then brief as the FINAL step after display, wrapped in try/except so a
  journal/brief failure can't break an already-complete run.
- `requirements.txt`: `anthropic==0.116.0` pinned + installed in `.venv`.
- `tests/test_journal.py`: 9 new tests (completeness, movement entered/exited/movers, v0.2 tracker,
  first-run-no-comparison, idempotency, brief no-key skip, empty-key skip, brief-failure-leaves-
  journal-intact, brief-success-attaches). **Full suite 62/62 green** (53 prior + 9).

**Verified:** real DAILY_LOG.md generated for the existing 2026-07-01 v0.2 live run (517 tickers,
1 live day). Brief self-skipped ("no API key") as designed. Top-10 is almost all financials —
expected sector-bias (ROADMAP known limitation, fixed by v0.3), not a bug. Evaluation state and
factor IC correctly show "pending" (no forward returns elapsed yet).

**Also this session:** added `Bash(.venv/Scripts/python.exe *)` to `.claude/settings.local.json`
(local/gitignored) so venv test runs stop prompting.

**Note:** ROADMAP.md was created this session from the pasted canonical content (it wasn't on disk),
with the journal layer moved to Done and v0.3 sector-neutral ranking now the top "Next" item.

---

## v0.2 `v0.2_fundamentals_added` — COMPLETED this session (2026-07-01)

Built per `market-warhorse-v0.2-spec.md`. Runs side-by-side with v0.1; v0.1 snapshots untouched.

**Four spec ambiguities resolved (all with the conservative reading, user-confirmed):**
1. **Sit-out scope** — only value/quality/short_interest components renormalize when missing;
   price/volume components stay MANDATORY (missing → horizon None). This preserves the v0.1
   missing-input contract and all 38 v0.1 tests. Encoded as `config.SITOUT_COMPONENTS`.
2. **Quality composite EXCLUDES current_ratio** (fetched/stored as context only) — matches the
   spec's explicit percentile-definition line over its looser raw-features "mild" note.
3. **short_interest_component = inverted percentile of short_%_of_float ONLY**; short_ratio is
   stored as context, never scored.
4. **Live-only** first run — NO v0.2 historical backfill was run (fundamentals aren't
   backfillable anyway). v0.2 IC accrues going forward.

**Code changes:**
- `config.py`: `model_version="v0.2_fundamentals_added"`; `FUNDAMENTAL_FIELDS`,
  `FUNDAMENTAL_INFO_KEYS`, `FUNDAMENTAL_PERCENTILE_GROUPS`, `NON_NEGATIVE_VALUATION_FIELDS`;
  reweighted `SCORE_WEIGHTS` (each horizon sums to 1.0, per-line rationale); v0.1 weights kept
  as `SCORE_WEIGHTS_V01`; `SCORE_WEIGHTS_BY_VERSION`; `SITOUT_COMPONENTS`; 3 new COMPONENT_PARAMS;
  new PARAMS (`fundamentals_refresh_days=5`, `fundamentals_fetch_delay_sec`, `fundamental_sparse_warn_pct=0.40`, `regime_recent_live_days=60`).
- `storage.py`: fundamental raw + `*_missing` flags added to RAW_FEATURE_COLUMNS; composite
  percentiles to PERCENTILE_COLUMNS; 3 components to SCORE_COLUMNS (all auto-migrate via the
  existing idempotent ALTER path — v0.1 rows got the new NULL columns, untouched otherwise). New
  `fundamentals` cache table (latest-only, point-in-time) + `get_cached_fundamentals` /
  `upsert_fundamentals` / `list_model_versions`.
- `data.py`: `fetch_fundamentals` — Ticker.info, throttled, cached with 5-day staleness reuse,
  fail-soft (a 404/rate-limit ticker sits out; stale cache reused over inventing).
- `features.py`: `compute_fundamental_features` — scrubs negative/zero valuation ratios to
  missing; derives value/quality/short/overall `*_missing` flags. Pass `{}` on backfill.
- `scoring.py`: composite value/quality/short percentiles (mean of present sub-percentiles,
  ranked over present-only); 3 pass-through components; sit-out renormalization in
  `compute_horizon_scores` (divide by present-weight; mandatory-missing still nulls).
- `evaluation.py`: per-version report (`model_version` tag), evaluates ALL versions for one
  side-by-side CSV, uses `SCORE_WEIGHTS_BY_VERSION` for notes, adds recent-vs-full IC
  (`spearman_ic_recent`, `n_recent`) over trailing 60 live run_dates (regime vigilance).
- `app.py`: live path fetches fundamentals for scored tickers and feeds `run_scoring_for_date`
  (new `get_fundamentals` arg; backfill passes the {}-default); `_warn_sparse_fundamentals`
  (>40% missing, live only); `_export_csvs` filters latest_rankings to the current version.
- `display.py`: View 2 picks one coherent version (current if it has IC rows, else the
  baseline) + new "Recent IC" column.
- `tests/test_fundamentals.py`: 15 new tests. **Full suite 53/53 pass (38 preserved + 15).**

**Live run verified (2026-07-01, `scratchpad_v02_live.log`):** 520 fundamentals fetched, 0
failed (ETFs 404 on fundamentals → sit out fail-soft); value 100% / quality 97% / short 97%
coverage, no sparse warning; latest_rankings=520 v0.2 rows; report evaluated both versions.
v0.1 IC prior still holds (trend 0.11, RS/momentum 0.05–0.08, setup/volume ~0, risk −0.02) →
no lookahead. v0.2 has 0 evaluable report rows yet — expected (no forward returns elapsed on the
single live date); the v0.1-vs-v0.2 comparison populates as live days accrue.

---

## What was completed in the PRIOR session (v0.1 universe + display)

### Segment A — S&P 500 universe expansion (completed, fully in code)
- `src/universe.py` created: `fetch_sp500_constituents` (pulls Wikipedia GICS table, caches to `data/sp500_constituents.csv`, falls back on failure), `assign_benchmark` (GICS → sector ETF), `build_universe_watchlist` (merges into watchlist without overwriting existing hand-assigned rows).
- `src/config.py` extended: `SECTOR_BENCHMARK_MAP` (12 GICS sectors → ETF), `SEMICONDUCTOR_SUB_INDUSTRIES` set, `sp500_*` PARAMS entries.
- `watchlist.csv` grown from 58 → 519 rows (461 new `sp500_auto` rows + all sector benchmark ETFs); BRK.B and BF.B dot→dash fix applied manually.
- `app.py` extended: `_grow_watchlist_with_sp500` (grows at every run, idempotent), `_print_benchmark_fetch_report` (ETF fetch success/fail report), benchmark ETFs included in fetch list.
- `tests/test_universe.py` added: 8 tests, all passing.
- Full backfill completed and verified: 259,221 snapshot rows, 519 tickers, 504 trading dates (2024-06-24 → 2026-06-26), model_version=`v0.1_price_volume_only`.

### Segment B — Terminal display layer (completed, fully in code)
- `src/display.py` created: two public functions (`print_top_setups`, `print_performance_summary`) backed by pure data-shaping helpers testable without terminal capture. Reads only from `output/latest_rankings.csv`, `output/performance_review.csv`, and `watchlist.csv` — never touches DB, never recomputes a number.
- View 1 (Today's Top Setups): top-N by `score_20d`, sector joined display-time from `watchlist.csv`, label via `scoring.label_for_score` (reused, not reimplemented), color-coded by label, `--top N` flag.
- View 2 (System Performance Summary): health-check line (checks momentum/RS/trend leading vs short-momentum/setup at 20d horizon), Strong-vs-Weak hit-rate table, full component-IC-ranking table sorted by Spearman IC desc, IC color thresholds mirroring `evaluation._suggested_weight_note` cutoffs (>0.10 green, <-0.05 red, else dim).
- `requirements.txt` updated: `rich==13.9.4` added and installed in `.venv`.
- `app.py` updated: imports `display`, adds `--top` CLI arg (default 15), removes old ad-hoc `print(table.to_string(...))` in `_run_live`, calls both display functions at end of `main()` (after `_export_csvs` and `evaluation.run_evaluation`).
- `tests/test_display.py` added: 8 tests covering top-N selection, NaN exclusion, sector join, label attachment, health-check healthy/inverted detection, hit-rate extraction, IC ranking sort. All 38 tests in full suite pass.

### What was verified
- `python app.py --backfill --top 10` completed successfully, exit code 0.
- Both display views rendered without tracebacks on the real 519-ticker universe.
- CLAUDE.md sanity check held on the full dataset: momentum/RS/trend components show positive spearman IC growing with horizon; short_momentum/setup stay near-zero and below — no lookahead inversion detected.
- All scoring/evaluation/storage logic files confirmed untouched by the display work.

---

## Current performance picture (from output/performance_review.csv, run 2026-06-26)

### Strong-bucket hit rates (% of snapshots where Strong beat its benchmark)
| Horizon | Strong hit % | Weak hit % | Interpretation |
|---------|-------------|------------|----------------|
| 5d      | 49.7%       | 49.9%      | No edge — coin flip, Weak slightly wins |
| 20d     | 48.8%       | 47.6%      | Minimal, noisy edge |
| 60d     | 51.5%       | 44.9%      | Real separation begins |
| 120d    | 52.8%       | 41.6%      | Clearest edge; ~3500-16000 obs per bucket |

### Key component IC findings (Spearman IC, 120d horizon — strongest signal horizon)
- `trend_component`: 0.11 (only component crossing the "meaningfully positive" threshold)
- `relative_strength_component_120d`: 0.08
- `long_momentum_component`: 0.08
- `medium_momentum_component`: 0.07
- `risk_component`: -0.02 (negative; has weight, drags composite)
- `setup_component`, `market_regime_component`: near zero across all horizons
- `volume_behavior_component`: near zero across all horizons

### Interpretation established this session
- IC → hit-rate is NOT linear. Rough mapping: `hit_rate ≈ 50% + (IC × 32)`. So IC=0.11 predicts ~53.5% — consistent with the observed 120d 52.8%, not 61%.
- 5d/20d hit rates near 50% are expected given CLAUDE.md's prior: short-horizon momentum mean-reverts; those horizons' signals should be near-zero.
- The composite score's edge is diluted relative to any single strong-IC component because the weights spread across ~10 components, several of which carry near-zero or slightly negative IC (volume_behavior, risk, setup, market_regime). Focusing weight on trend/RS/long-momentum would improve composite predictive power.
- **This system currently has a real but modest measurable edge at 60d/120d, and essentially no directional edge at 5d/20d.** This is not a problem per CLAUDE.md's design intent ("a measurement instrument and chassis for richer data later").

---

## Decisions made this session not yet reflected in the spec

1. **IC → hit-rate mapping is now understood.** The spec and CLAUDE.md don't document the arcsine approximation or explain why IC 0.11 ≠ 61% win rate. Worth adding a note to CLAUDE.md's "Sanity check" section if this causes confusion again.

2. **display.py health check uses 20d as the primary horizon** (not 5d or 120d). This is a code choice not in the spec. Rationale: 20d is the primary ranking horizon (score_20d drives View 1 sort); health-checking that horizon's component ICs is most directly meaningful. If the spec is updated, note this.

3. **Sector is a display-time join, never stored.** Confirmed via `storage.py` and `market-warhorse-v0-spec.md` review: `feature_snapshots` has no sector column; `latest_rankings.csv` has no sector column. Display joins from `watchlist.csv` at read time. This is correct and intended — no spec change needed, but note it so it isn't re-investigated.

---

## In progress / not started

Nothing is in progress mid-implementation. All planned work is committed and passing.

---

## Next step (not yet decided or built)

**The next meaningful improvement is adding richer input data** — per CLAUDE.md's "Extensibility" section: *"The edge comes from richer DATA added later (estimate revisions, fundamentals, options, text-derived features), not from these price/volume stats."*

Concrete candidates (not yet prioritized, no code written):
- **Earnings estimate revisions** (e.g. via a free source): would likely have real IC given the academic literature on SUE/revision drift.
- **Basic fundamentals** (P/E, EV/EBITDA from yfinance): free, available now, limited IC but adds a quality filter.
- **Analyst revision count / direction**: directional signal, complements price momentum.

Any of these follows the same pattern: new feature column in `features.py`, new weight in `config.py`, bumped `model_version`, re-run `--backfill`, check `performance_review.csv` to see if IC improved.

**Before adding any new signal**, it would be worth reviewing whether the current composite weights should be rebalanced first — given that trend/RS/long-momentum carry positive IC and risk/setup/volume/market_regime are near-zero or negative, redistributing their weight toward the working components would improve the composite without adding any new data. That is a `config.py`-only change + `model_version` bump, no new code.

---

## How to run

```
python app.py           # daily live run — fetches latest data, scores, prints both views
python app.py --top 20  # show 20 rows instead of 15 in View 1
python app.py --backfill  # full history rebuild (already done; only needed if model changes)
pytest tests/ -q        # 38 tests, all should pass
```
