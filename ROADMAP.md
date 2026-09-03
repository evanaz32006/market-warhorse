# market-warhorse — ROADMAP

Permanent record of committed-but-not-yet-built items, known limitations, and their rationale.
Every Claude Code session should read this alongside CLAUDE.md. Items move to "Done" only when
verified, never deleted — this file is the project's memory.

---

## Done
- **v0.1_price_volume_only** — 519-ticker S&P 500 universe, full 504-date backfill (259,221 snapshots),
  verified no-lookahead harness, IC/hit-rate evaluation, display layer (rich), 38/38 → tests green.
  Key finding: momentum/RS/trend carry positive IC growing with horizon; volume/setup ≈ 0.
- **v0.2_fundamentals_added** — value / quality / short-interest components (live-only), sit-out
  renormalization, principled reweight (volume/setup cut, risk reduced-not-inverted), recent-vs-full
  IC drift columns. 53/53 tests green.
- **Daily journal + AI brief layer** — `src/journal.py` writes one structured entry per
  (run_date, model_version) to a `journal` SQLite table + regenerates `output/DAILY_LOG.md`
  (idempotent: re-running a date replaces its entry). Entry sections: run metadata (mode, runtime,
  fetch summary, warnings), rankings movement (top-10, entered/exited vs previous live run, biggest
  single-day movers joined on ticker), evaluation state (per-horizon hit rates + full-vs-recent IC
  drift flags), and the v0.2 live-validation tracker (live-day count + live-only value/quality/short
  IC). `src/brief.py` optionally summarizes the entry via the Claude API (`claude-sonnet-4-6`,
  system prompt per spec, never a buy/sell recommendation) and embeds it under **Brief:** at the top
  of the day's entry; degrades gracefully (no key / package absent / API error → one-line note, run
  never fails). Wired as the final step of `app.py` after display. `anthropic==0.116.0` pinned.
  62/62 tests green (9 new: completeness, movement, idempotency, brief skip/failure/success).
  Read-only consumer of existing outputs — no scoring/evaluation/storage VALUES changed.

## Known limitations (permanent context — do not "fix" by inventing data)
- **Fundamentals do not backfill.** yfinance gives current-only fundamentals/short interest/earnings
  dates. v0.2's new factors validate on LIVE data only, one trading day at a time. Backfilled v0.2
  rows ≈ v0.1. The binding constraint on validating v0.2 is calendar time, not features.
- **Value/quality ranking is currently sector-biased** (plain cross-sectional). Utilities/banks look
  structurally cheap, tech structurally expensive. (Visible already: the first v0.2 live top-10 is
  almost entirely financials.) Fixed by v0.3 sector-neutral ranking.
- **Risk component shows negative IC in the 2024–26 backfill window.** Treated as regime artifact;
  weight reduced, deliberately NOT inverted (anti-overfit decision, logged in v0.2 spec).
- **Universe has survivorship flavor** — constituents as of today, so backfilled IC is mildly flattered.

## Next (committed, in order)
1. **Automated daily run** — Windows Task Scheduler, weekdays ~6pm ET, full python.exe path,
   start-in C:\Warhorse. Removes the human single-point-of-failure. Missed days = holes in the only
   dataset that can validate v0.2. (OS-level task, no code change.) With the journal now in place,
   each scheduled run leaves a dated audit trail in DAILY_LOG.md.
2. **v0.3 — sector-neutral ranking** for value/quality (rank within GICS sector, then combine).
   Clear win, low overfit risk. Directly improves the factors currently accruing live validation.

## Later (evidence-gated — do not build until the IC earns it)
- **`operating_margin` — verify against a third source, then likely PREFER the EDGAR figure.**
  Withheld from v0.4 (`EDGAR_EXCLUDED_FIELDS`) because it failed all three gate criteria: EDGAR runs a
  systematic ~9% BELOW yfinance for 75% of names (Spearman 0.860, median diff 14.2%). The gap survived
  every fix including period alignment, so it is a definitional difference, not a bug — yfinance almost
  certainly publishes a NORMALIZED operating income (one-time charges excluded) against us-gaap
  `OperatingIncomeLoss`, which is as-reported. yfinance showing NEGATIVE margins for PANW and COO —
  both profitable, both heavy on stock comp and acquisition amortization — is exactly that split.
  **If confirmed, EDGAR's as-reported number is the BETTER input**: it is consistent, auditable, and
  point-in-time, while Yahoo's normalization is opaque and unversioned. Re-enabling is a config edit
  plus a re-derive — the raw facts are already stored, so no re-ingest.
- **Sector-specific component weighting** — plausible but multiplies tunable knobs (11 sectors ×
  components) = high overfit risk. Only pursue factor-by-factor with IC evidence per step.
- **Earnings/revisions data layer (v1.x)** — the most likely revival path for the 5d/20d horizons
  (short-horizon moves are catalyst-driven). Free-first (yfinance revisions fields), paid later
  (Zacks etc.) only if the free version shows promise in the harness.
- **AI feature-extraction layer** — LLM-derived features from transcripts/filings/news. This is the
  edge-relevant AI layer; requires the data layer and clean point-in-time discipline first. (Distinct
  from the AI *brief*, which is legibility only and adds zero edge.)
- **Insider transactions / options-IV / seasonality** — deliberately excluded from base (weak or
  messy free data). Each may enter only as its own tested version.

## Standing disciplines
- **Every new data source ships behind a PRE-REGISTERED validation gate.** Not a one-off for EDGAR —
  a standing rule. The v0.4 gate compared EDGAR-derived fundamentals against the yfinance cache under
  a pass bar written down BEFORE the numbers were seen (median abs diff < 10%, Spearman > 0.90,
  >100%-diff tail < 5%). It caught **five** real bugs, **two of which would have silently corrupted a
  two-year backfill**:
  1. *Dead-tag staleness* — filers abandon XBRL tags but the old facts live forever. First-tag-wins
     returned NVDA a 1,603-day-old revenue labelled `method="annual"` with full confidence (603%
     operating margin). 40 of 360 filers shared the pattern.
  2. *Negative-equity rank inversion* — `debt_to_equity` is an INVERTED quality field, so Clorox's
     negative book equity (−3,711) would have ranked the most-levered name in the index as its safest.
  3. `debt_to_equity` built from total Liabilities as a raw ratio, not interest-bearing debt × 100.
  4. REIT revenue read from the ASC-606 contract tag (leases aren't contracts) → AVB profit margin 160x.
  5. Margin legs resolved from different periods for 51 of 507 filers — two different 12-month windows
     divided into one ratio.
  Both silent corruptions produce *beautiful, plausible* backfills. Neither is detectable downstream.
  The gate is the only thing that catches them, and it must precede every future source (FINRA short
  interest, estimate revisions, Form 4, 13F), not just this one.
- 5d horizon is a deliberate testbed, not dead weight — do not scrap it.
- Weights change gently, on principle + accumulating IC evidence; never one-shot curve-fit.
- v-versions run side-by-side; old snapshots immutable.
- The journal is a LENS, not a signal — presentation/logging only; it must never alter scoring,
  evaluation, or storage VALUES, and the AI brief must never phrase anything as a recommendation.
- Before ending any Claude Code session: write SESSION_STATE.md (what finished, what's in flight,
  decisions made, next step).
- Watch recent-vs-full IC drift as the regime-shift early-warning once live data accrues — the
  journal surfaces this per run.
