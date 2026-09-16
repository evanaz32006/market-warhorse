# SESSION_STATE.md

Last updated: 2026-09-16

---

## Sector timing — MEASURED, null, and underpowered by construction (2026-09-16)

`research.run_sector_timing_research`, `--research sectortiming`, 6 tests. **Report only.**

**Why:** since v0.3 the ranking is sector-NEUTRAL — it picks stocks within a sector and never
decides which sector to hold. The money view showed exactly that failure: a basket six-tenths
Energy, down while SPY rose. This asks the dimension the model deliberately ignores.

**What was tested:** two predictor families across the 12 sector ETFs, per day, as a
cross-sectional Spearman IC against forward excess vs SPY — trailing sector momentum at 20/60/120/
252 sessions, and constituent breadth (% above SMA200 / SMA50) from the stock panel. Plus the
tradeable version: non-overlapping top-3-minus-bottom-3 holds, for an honest independent count.

**Pre-registered:** long lookbacks (120–252d) positive at 20–120d forward; 20d lookback weak or
reversing; breadth weakly positive. Power stated up front as low — twelve points per day.

**Result: 24 cells, 17 testable, 0 nominally significant against 0.9 expected, 0 survive.** Seven
cells at 120d fell below the inference floor entirely (effective n 1.6–3.5).

The one direction-consistent cell is the pre-registered one: **252d momentum → 5–20d forward,
IC +0.062 / +0.063, 58–61% of days positive, non-overlapping top-minus-bottom +0.44% at 5d over 61
windows.** Right sign, right lookback — and about half the minimum detectable IC (0.146). Not
evidence; not counter-evidence.

**The MDE column is the finding.** With 12 sectors the minimum detectable IC is 0.10–0.15 at short
horizons and 0.3–0.6 at 60–120d. The published sector-momentum effect is roughly IC 0.05–0.10 and
lives at 1–6 months. **This sample cannot see it where it lives**, same shape as the Form 4 result.
Moskowitz & Grinblatt needed three decades; this is 2.2 years.

**The way out is different here, though.** The sector ETFs are 12 series with ~27 years of free
daily history on Yahoo (SPDRs launched 1998). `fetch_period = 2y` is a project choice made for a
1,500-name universe, not a data limit — and a sector-level study needs no stock panel. Extending
the momentum family to the full ETF history would take effective n at 120d from ~3 to ~50, at the
cost of ~90k rows. Kept OUT of `price_history` deliberately: the master calendar is SPY-derived and
extending it to 1993 would ripple into every panel loader. Next step if pursued: a separate cache.

---

## SEC 8-K material events — INGESTED and MEASURED (2026-09-11)

`src/filings.py` + `tests/test_filings.py` (14). `python app.py --ingest-filings`, then
`--research events`. **Report only.** 65,549 filings across 1,498 of 1,509 names, 2023-12-01 ..
2026-09-10.

**Source:** the per-company submissions API, because it carries the 8-K ITEM CODES. The quarterly
bulk index lists filings but not items, and the item code is the entire signal — a 5.07
(annual-meeting vote) and a 4.02 (previously issued financials can no longer be relied upon) are
both "an 8-K". Unlike the Form 4 bulk datasets this source is CURRENT (through today), so a feature
built on it could serve a nightly run without a second pipeline.

**The one-day leak this could have had.** SEC stamps an 8-K accepted at 16:35 ET with THAT DAY's
`filingDate`, but the market shut at 16:00. `effective_date` rolls anything accepted at or after the
close to the next session, and rolls weekend/holiday filings forward. Small, invisible in output,
and exactly the size that makes a short-horizon event study look real.

**Routine is not material.** Item 9.01 is an attachment notice bolted onto most other items; 5.07 is
the annual shareholder vote. Features count six item GROUPS separately rather than pooling them —
the same discipline as splitting insider code P from grants.

### The result: nothing, and THIS null is informative

108 cells (6 groups x 3 windows x 6 horizons), 105 testable. **3 nominally significant against 5.2
expected by chance — fewer than chance would produce. Zero survive BH-FDR.**

The pre-registered reading said 8-K news is incorporated within hours, so a daily-resolution feature
should find little. That is exactly what happened, which is a correctness signal for the harness
rather than a disappointment.

The most extreme cells, all failing correction:

| group | window | h | spread | hit | t | eff n | MDE |
|---|---|---|---|---|---|---|---|
| earnings (2.02) | 5d | 1 | **-0.054%** | 48.2% | -2.13 | 541 | 0.071% |
| earnings (2.02) | 5d | 2 | -0.096% | 48.1% | -2.04 | 270 | 0.132% |
| redflag (4.02/2.06/1.03/3.01) | 5d | 1 | **-0.40%** | 43.7% | -1.77 | 48 | 0.635% |

**Why this null is worth more than the insider null.** The Form 4 study could not have detected its
own hypothesis: MDE 0.039-0.062 in IC terms at 60-120d against a literature effect of ~0.02-0.03.
Here the sample HAS power where the hypothesis lives — 541 effective independent observations at
h=1, MDE 0.07%. **We could have seen a tradeable effect and did not.** That is a real answer, not a
shrug.

The one cell that stays open is `redflag`: only 48 qualifying days and 167 event-name-days, MDE
0.635% against an observed -0.40%. Right sign, right story, too rare to confirm. Rare severe events
need years, not names.

Even the significant-looking earnings cell is not tradeable: -0.054% is the same order as the
round-trip cost of the trade.

### Coverage notes

Four names returned nothing, all correctly: **ARM and TSM are foreign private issuers** (they file
6-K/20-F, never 8-K or 10-Q), and **OZK and PFBC are state banks with no holding company**, which
file their periodic reports with the FDIC rather than the SEC. Their EDGAR presence is only
13F-HR/13G. Any 8-K feature is permanently null for these four — correct behaviour, but a coverage
asymmetry to remember.

---

## CIK MIS-MAPPING: two live names were pointed at the wrong company (2026-09-11)

Found while chasing the four zero-filing names above. **This is a data-integrity bug in the live
model's mapping, and it was one refactor away from producing confidently wrong numbers.**

`_norm_ticker` strips punctuation so `BRK-B` can find `BRKB` — a deliberate earlier fix. But SEC's
`company_tickers.json` also lists **preferred-share tickers**:

| SEC ticker | normalizes to | company | CIK |
|---|---|---|---|
| `BCPC` | BCPC | **Balchem** | 0000009326 |
| `BC-PC` | BCPC | Brunswick preferred series C | 0000014930 |
| `TPC` | TPC | **Tutor Perini** | 0000077543 |
| `T-PC` | TPC | AT&T preferred series C | 0000732717 |

`build_cik_map` assigned into a flat dict, so whichever entry came last won. Result: **Balchem was
mapped to Brunswick's CIK, and Tutor Perini to AT&T's.** Two of four such collisions in SEC's entire
table land in our universe.

**Why it produced no wrong number — pure luck.** `edgar_facts` is written with a `ticker` column and
read back BY TICKER (`storage.load_edgar_facts(ticker=...)`), while ingest is deduplicated BY CIK.
Brunswick and AT&T had already been ingested under their own tickers, so BCPC/TPC were skipped as
"fresh" and no rows exist under those tickers. The resolver therefore returns nothing and the
fundamentals are NULL. **A future cleanup keying the read on CIK — the obvious refactor — would have
activated it instantly and started scoring Balchem on Brunswick's books.**

Fixed: exact ticker match wins; a normalized match is used only when every candidate resolves to the
SAME CIK; a genuinely ambiguous one is REFUSED and logged loudly rather than guessed. Four tests,
including the exact BCPC/TPC case. Safe to land now because `build_cik_map` is never called from the
nightly path — only from an explicit EDGAR ingest — so nothing in the live model changes until a
deliberate re-ingest.

### The related open item, NOT fixed (it is a fork)

Reading facts by TICKER also breaks **dual-class and shared-CIK siblings**. The CIK is correct, but
the facts are stored under whichever ticker the ingest loop happened to be on, so the sibling
resolves nothing:

| ticker | shares CIK with | facts under our ticker | profit_margin NULL |
|---|---|---|---|
| GOOG | GOOGL | 0 | 538 of 553 |
| FOX | FOXA | 0 | 539 of 553 |
| UAA | UA | 0 | 500 of 515 |
| CENTA | CENT | 0 | 500 of 514 |
| VMRK | EQR | 0 | 500 of 515 |

So **five live names carry null value/quality components for no real reason** — the data is sitting
in the database under a sibling ticker. GOOG and GOOGL are the same company and currently get
different scores purely because of a storage key.

The fix (read by CIK) is one line, but it **changes fundamentals for ~7 names, which changes their
scores** — a new `model_version` under CLAUDE.md #5, not an edit to v0.5. And it MUST land after the
mapping fix above, never before, or it activates the Balchem/Brunswick bug. Left for the owner.

---

## SEC Form 4 insider transactions — INGESTED and MEASURED (2026-09-10)

`src/insider.py` + `src/backup.py` + `tests/test_insider.py` (18) + `tests/test_backup.py` (6).
`python app.py --ingest-insider`, then `--research insider`. **Report only.** No feature column, no
`model_version` bump, nothing deployed.

### Source choice

SEC publishes QUARTERLY structured Form 345 datasets — every ownership filing already parsed into
TSVs. **Nine downloads (~94 MB) cover the whole price history.** Enumerating the same filings
through the submissions API would have been roughly 200,000 HTTP requests against an 8/s throttle:
days of wall clock for byte-identical data.

Ingested **480,796 rows across 1,483 of 1,509 universe names, filed 2024-01-02 .. 2026-03-31.**

### Four traps in this dataset, all of which produce plausible wrong numbers

1. **`FILING_DATE` vs `TRANS_DATE`.** An insider has two business days to report. Gating on the
   trade date grants several days of foresight per filing — a textbook leak. The gate is
   `filed_date`, and `test_a_filing_is_invisible_until_its_filing_date` asserts it directly.
2. **Compensation is not an opinion.** Measured code mix: S 82,879 / A 62,301 / F 57,748 /
   M 43,112 vs **P 6,542**. Grants, option exercises and tax withholding outnumber genuine
   open-market purchases **25:1**. Counting all "acquisitions" would have buried the one code with
   a documented anomaly behind an order of magnitude of payroll noise.
3. **Two independent duplication paths.** 1,151 of 63,284 filings in a single quarter carry
   MULTIPLE reporting owners (up to 10) — keying storage by owner multiplies one trade's shares by
   up to 10x. Separately, affiliated entities file separately for the SAME economic trade under
   different accession numbers (two Apollo entities, the same 1,185,242-share TBLA disposition), so
   aggregation dedupes on the trade's own attributes; the accession number cannot distinguish them.
4. **SEC's `ISSUERTRADINGSYMBOL` is filer-typed free text.** It arrives as `(CALX)`, `-`,
   `BFA, BFB`, `BIO BIO.B`, `BRK.A`. Joining on it returned **ZERO insider rows for 35 of our
   names** whose filings were in the store the whole time — a coverage hole that looks exactly like
   a company whose insiders never trade. Ticker is now resolved from CIK; SEC's string is kept as
   `sec_symbol` for audit only, never as a key.

### Coverage gap, stated rather than hidden

SEC publishes on a lag. Verified 2026-09-10: 2024Q1–2026Q1 exist, 2026Q2/Q3 return 404. So the store
ends **2026-03-31** while prices run to 2026-09-08. Reads past coverage return `None` with
`coverage_missing=True`, **never 0** — 164,799 of 797,530 panel rows were dropped on that basis
rather than zero-filled. An absence of data is not an absence of buying (CLAUDE.md #2).

### The result: no usable signal — but read the reason carefully

Pre-registered reading (written before the numbers): insider buying should show POSITIVE IC GROWING
with horizon, peaking 60–120d, strongest for officers.

Observed, on 632,731 covered name-days over 444 run dates:

| feature | h=5 | h=20 | h=60 | h=120 |
|---|---|---|---|---|
| `insider_buy_count_90d` IC | 0.0066 | 0.0029 | 0.0034 | 0.0024 |
| `insider_officer_buy_count_90d` IC | 0.0045 | -0.0015 | **-0.0125** | **-0.0152** |
| `days_since_insider_buy` IC | -0.0131 | -0.0162 | -0.0134 | -0.0029 |

**Every |t| < 1.5.** The shape is wrong too — decaying with horizon rather than growing, and the
officer measure (the literature's STRONGEST prediction) turns negative at 60–120d.

Event study — names with ≥1 open-market purchase in the trailing 90d vs names without, 95,845
name-days with a purchase: +0.09% at 5d (t=1.46), +0.07% at 20d, +0.22% at 60d but with a
**negative median (-0.08%) and a 47% hit rate**, i.e. the 60d mean is a few large winners rather
than a broad effect. At 120d, +0.03% mean against a -0.33% median.

### The honest caveat, and it is the important part

`min_detectable_ic` — the smallest true IC this panel could detect at 80% power — is:

| horizon | effective independent n | min detectable IC |
|---|---|---|
| 5d | 88.8 | 0.014 |
| 20d | 22.2 | 0.021 |
| 60d | 7.4 | **0.039** |
| 120d | 3.6 | **0.062** |

The published insider-buying anomaly corresponds to a cross-sectional IC of roughly 0.02–0.03.
**At 60–120d — exactly where the effect is supposed to live — this sample could not have detected it
even if it is entirely real.** So the correct statement is NOT "insider buying does not work". It is
**"2.25 years of data cannot answer this question at the horizons that matter."** At 5d, where the
sample IS adequate (MDE 0.014 vs observed 0.0066), there is genuinely nothing — but nobody claims
the effect lives at 5d.

This is the fifth hypothesis measured and not confirmed, and the first one where the limiting factor
is provably the sample rather than the signal. **Only calendar time fixes it.** The store is built,
gated and tested, so re-measuring later costs one command.

### Database backup — DONE (`src/backup.py`, `python app.py --backup <DEST>`)

`VACUUM INTO`, never a file copy: in WAL mode the `-wal` sidecar holds committed pages not yet in
the main file, so a plain copy silently loses recent writes — `test_backup_survives_wal_mode` writes
rows without checkpointing and asserts they survive. Every backup is then reopened,
`PRAGMA integrity_check`-ed and row-count-matched against the source, and **raises** on failure
rather than reporting it in a field nobody reads. Also fixed a real bug found by its own test: two
backups in the same second collided on the timestamp and `VACUUM INTO` failed opaquely.

**Still needs to actually be RUN, to a different physical device.**

### Also written: `RUNBOOK.md`

The "operate this alone" document. What to run daily (`--status`), weekly (`--backup`), how to read
`performance_review.csv` without fooling yourself, what breaks and what to do, and the five things
that will bite an operator with no memory of the build.

---

## Conditional-pattern test harness — BUILT and first results in (2026-09-09)

`src/patterns.py` + `tests/test_patterns.py` (18 tests). Opt-in via `python app.py --research
patterns`. **Report only** — it reads `price_history` and NOTHING else, so it is unaffected by which
`model_version` is live and does not need re-running when a version is promoted.

**Why a harness rather than one feature per idea.** The owner has many "after X, does Y happen?"
hypotheses. Hand-coding each is a day of work; as a query it is minutes. But making a test cheap
makes a FALSE discovery cheap — 200 seasonal patterns at alpha=0.05 hands back ~10 "findings" that
measured nothing. So the correction machinery is a first-class output, not advice in a docstring:

- **per row** — `effective_independent_n` by GREEDY NON-OVERLAP SCAN, which is sharper than the
  blanket `n_days / horizon` used elsewhere in this project and has to be: a Friday-only condition
  at h=5 fires weekly and its windows barely overlap, so the blanket rule would discard 80% of a
  real sample. Plus `min_detectable_effect_pct` at 80% power, which is what separates "no effect"
  from "no effect large enough to see with 554 sessions".
- **per family** — Bonferroni, Benjamini-Hochberg FDR, and a circular-shift null on the family's
  max |t| (White's Reality Check in spirit). ONE SHARED offset per replication, deliberately:
  independent shifts would destroy the correlation between patterns tested on the same tape and
  produce a null that is too WIDE — conservative-looking but wrong.
- **always** — a chronological out-of-sample split, reported per row (`sign_held_oos`).
- **p-values use the Student-t tail, not the normal approximation.** At 7 df the 5% two-sided cutoff
  is 2.36, not 1.96. Every sample in this project is small, which is exactly where the normal
  approximation calls a t of 2.1 significant when it is not.

### Three defects the harness found in its own first live run

1. **A two-observation "SIGNAL".** "SPY down 5 sessions in a row" fired exactly TWICE in 554
   sessions, both followed by a gain. A two-point standard deviation gave t = 185 and handed the
   whole `streaks` family a p = 0.010 SIGNAL verdict built on two coin flips. Fix:
   `pattern_min_effective_n` = 5 — below that a row is described but gets no t, no p, and **no vote
   in the family correction** (it would otherwise also inflate Bonferroni's divisor and supply the
   family's max |t|). With the floor applied, `streaks` went 0.010 -> 0.559.
2. **A series measured against itself.** `sector_day_of_week` included SPY, whose excess return vs
   SPY is identically zero — zero variance, no t, and the row silently landed in the "could not be
   tested" bucket as though the data were thin rather than the comparison meaningless. Five such
   rows. Fixed, and `_inference_note` now NAMES which of the two causes applies.
3. **A too-wide null hiding behind small-n rows.** Because the untestable rows were originally in
   the permutation family, the null's max |t| was inflated by their garbage t-values. Removing them
   narrowed the null correctly — which moved `strong_week_reversal` the OTHER way, from 0.174 to
   0.038. Worth recording: the fix made one family look worse and another look better, which is what
   a real fix does rather than one tuned toward a desired answer.

### The results (198 tests, 6 pre-declared families)

**8 of 192 tested rows are nominally significant. 9.6 are expected by chance. ZERO survive
Bonferroni or BH-FDR.** That is the textbook picture of no signal.

- **"Historically weaker Fridays" is not in this data** — and the sign is backwards. Friday is the
  *strongest* weekday for SPY: +0.19% mean vs a +0.07% baseline, 65.5% hit rate vs 56.8%. t = 1.42,
  p = 0.16 — not significant either way. The weak day is Wednesday (t = -1.44). Family p = 0.499.
- **Month-of-year and turn-of-month: nothing** (family p = 0.810), and all 12 month rows are
  underpowered by construction — 554 sessions is TWO observations per calendar month.
- **Regime (above/below SMA50/200): nothing** (family p = 0.986).
- **`strong_week_reversal` family p = 0.038, and it should NOT be read as a finding.** The driver is
  a single n=5 row (XLY strong week + Thursday -> Friday, 100% hit rate on five observations) sitting
  exactly at the inference floor. The family's own null p95 is |t| = 5.0 — this family produces
  |t| ~ 5 by chance routinely — and the observed 6.03 barely clears it. Nominally significant count
  is 3 against 3.4 expected: exactly chance.

### The one thing worth watching

Inside that family, three RELATED tests point the same way with real sample sizes: after a
top-decile week, **mid- and small-cap indices give it back**.

| test | n / eff_n | lift | tradable | hit vs base | t | OOS sign |
|---|---|---|---|---|---|---|
| IJR top-decile own 5d week -> next 1d excess | 33 / 33 | -0.32% | -0.21% | 30% vs 46% | -2.60 | held |
| IJR best-of-peers 5d week -> next 5d excess | 17 / 9 | -1.05% | -1.10% | 24% vs 45% | -2.60 | held |
| IJH top-decile own 5d week -> next 1d excess | 30 / 30 | -0.19% | -0.16% | 30% vs 47% | -1.87 | held |

Same sign, same direction as the owner's hypothesis, sign held out of sample in all three, and the
effect survives the tradable (D+1 open) measurement rather than living only in the close-to-close
version. It still does **not** pass the corrected bar, and one coherent cluster inside a family whose
significant-row count is exactly chance-level is not evidence. **No weight change, no new feature.**
The honest status is "re-measure when there is more calendar time", which is also the only thing
that can settle it — adding names cannot.

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
