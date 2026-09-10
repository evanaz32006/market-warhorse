# market-warhorse — v0.2 Build Spec
## `v0.2_fundamentals_added`

This version completes the base layer by adding the durable factor families the price/volume-only v0.1
was missing (value, quality, short interest), then reweights all components on principle using the IC
evidence from the v0.1 full-universe backfill. It runs **side-by-side** with v0.1 — v0.1 is preserved as
the baseline, never overwritten.

---

## Guiding principles (read before building)

1. **Orthogonal factors, not more momentum.** v0.1's trend / relative-strength / momentum components are
   largely the same underlying bet (price has been going up). The point of v0.2 is to add signal that is
   *structurally independent* of momentum, so the system is robust across regimes rather than tuned to one.
2. **Durability over backfit.** Initial weights are set from cross-regime evidence and academic priors,
   NOT optimized to maximize IC on the 2024–2026 backfill. The backfill measures whether the priors hold;
   it does not get to dictate the weights in one shot. Overfitting to one regime is the primary failure mode.
3. **No-invent-data is absolute.** Fundamentals and short interest are sparser and flakier than price data.
   If a field is missing or stale for a ticker, that component sits out for that ticker (null + `*_missing`
   flag) — it is never estimated, defaulted, or guessed. A silently-wrong fundamental is worse than none.
4. **Selective, not exhaustive.** We add three orthogonal durable families. We deliberately exclude insider
   transactions, options/IV, and seasonality from the base layer (weak signal and/or messy free data). They
   can be added later as their own tested versions if the IC earns them a place.

---

## New data to fetch (`data.py` additions)

All from free yfinance endpoints (`Ticker.info`, `Ticker.get_shares_full`, etc.). Cache to SQLite alongside
price history. Respect existing batching/delay/retry/cache discipline — these are per-ticker `.info` calls
and are the most rate-limit-prone, so fetch them in the same throttled loop and cache aggressively.

**Fundamental fields (per ticker, latest available):**
- `trailing_pe`, `forward_pe`, `price_to_sales`, `price_to_book`, `ev_to_ebitda`
- `profit_margin`, `operating_margin`, `return_on_equity`
- `debt_to_equity`, `current_ratio`
- `earnings_growth`, `revenue_growth`

**Short interest fields (per ticker, latest available):**
- `short_percent_of_float`
- `short_ratio` (days-to-cover)

**Critical caveats to handle:**
- yfinance fundamental fields are point-in-time *as of fetch* — they are NOT historical. For the live run
  this is fine. **For backfill, fundamentals cannot be reconstructed historically from yfinance** (same
  limitation as earnings dates). Backfilled rows therefore use only price/volume factors and set
  `fundamentals_missing=True`. The fundamental/value/quality/short components apply to **live runs only**.
  Document this clearly — it means v0.2's new factors are validated going forward, not on the backfill.
- Many fields will be missing for some tickers (ETFs, recent IPOs, financials with non-standard metrics).
  Missing → null + flag, component sits out, never defaulted.

---

## New raw features

**Value (lower = cheaper = better, so these get inverted in percentile ranking):**
- Use `trailing_pe`, `price_to_sales`, `ev_to_ebitda`, `price_to_book`.
- Guard against negatives: a negative P/E (no earnings) is not "cheap" — treat negative valuation ratios as
  missing for that metric, not as a low (good) value.

**Quality (higher = better):**
- `profit_margin`, `operating_margin`, `return_on_equity` (higher better)
- `debt_to_equity` (lower better — invert)
- `current_ratio` (higher better, mild)

**Short interest (higher short interest = bearish signal = lower rank):**
- `short_percent_of_float` (higher = worse, invert in ranking)
- `short_ratio` (context, mild)

---

## New percentile ranks (intra-universe, cross-sectional, as of each run)

Add to the existing percentile set, computed only over tickers with the data present:
- `value_percentile` — composite: average the inverted percentile ranks of P/E, P/S, EV/EBITDA, P/B
  (cheaper → higher). Sector-neutralize if feasible (see note below); if not, plain cross-sectional.
- `quality_percentile` — composite: average percentile ranks of margins + ROE + inverted debt/equity.
- `short_interest_percentile` — inverted percentile of short % of float (less shorted → higher).

> **Sector-neutrality note (important for value/quality):** raw value/quality ranks are sector-biased —
> tech always looks "expensive," utilities always look "cheap," banks have alien margin structures.
> If practical, rank value and quality *within sector* (compare each stock to its sector peers) rather than
> across the whole universe. If full sector-neutral ranking is too complex for this pass, implement plain
> cross-sectional now and flag sector-neutralization as a v0.3 improvement — but note it, because it matters.

---

## New components (0–100)

**value_component:** `100 * value_percentile`. If value data missing → component null, sits out of the
weighted score (reweight remaining components proportionally for that ticker). Clamp 0–100.

**quality_component:** `100 * quality_percentile`. Missing → sits out. Clamp.

**short_interest_component:** `100 * short_interest_percentile`. Missing → sits out. Clamp.

> **"Sits out" means:** when a component is null for a ticker, the horizon score is computed from the
> remaining components with their weights renormalized to sum to 1. A ticker missing fundamentals still gets
> a valid (price/volume-based) score; it just doesn't get the value/quality contribution. This must be
> explicit and tested.

---

## Reweighted horizon scores (the principled reweight)

Rationale for every change is recorded so this is a documented decision, not a curve-fit. Weights are set
from cross-regime durability + the v0.1 IC evidence, deliberately conservative.

### What the v0.1 IC evidence said
- **trend / relative-strength / momentum:** consistent positive IC, growing with horizon (trend up to
  ~0.11 at 120d). Durable per momentum literature. → keep meaningful, nudge trend up at long horizons.
- **volume_behavior:** ~0.00 IC at every horizon. Arbitraged folklore. → cut hard.
- **setup_component:** ~0.00–0.02 IC. Chart-pattern folklore. → cut hard.
- **risk_component:** negative IC in this backfill. BUT low-vol is a durable long-run premium; the
  inversion is most likely regime. → reduce weight, **do NOT invert** (deliberate anti-overfit choice).
- **market_regime:** slightly negative / near zero. → cut to minimal.
- **short_momentum (5d):** ~0.00 IC. Price/volume can't predict 5-day moves — expected. → keep a small
  slot; this is the horizon the future earnings/revision data layer is most likely to revive. Do NOT scrap.

### New weights (live runs; renormalize when components sit out)

**score_5d** — kept deliberately, starved of the right inputs for now:
- short_momentum 15% · relative_strength_5d 15% · trend 15% · value 15% · quality 15% · risk 10% ·
  short_interest 10% · volume_behavior 5%
- (Down-weighted the dead price/volume short-horizon stuff; added value/quality/short as the orthogonal
  signal that *might* carry where momentum can't. This horizon is explicitly the testbed for the data layer.)

**score_20d:**
- trend 18% · momentum_20d 15% · relative_strength_20d 15% · value 15% · quality 15% ·
  short_interest 7% · risk 10% · volume_behavior 0% · setup 0% · market_regime 5%
- (Cut volume/setup to zero per IC. Added value+quality as 30% combined orthogonal signal.)

**score_60d:**
- trend 20% · medium_momentum 15% · relative_strength_60d 18% · value 17% · quality 15% ·
  risk 8% · short_interest 5% · market_regime 2%
- (Trend nudged, value/quality fold in as durable medium-horizon factors.)

**score_120d:**
- trend 22% · long_momentum 15% · relative_strength_120d 18% · value 15% · quality 15% ·
  risk 8% · short_interest 5% · market_regime 2%
- (Trend up to ~22% reflecting its 0.11 IC; value/quality as long-horizon bedrock.)

All horizons: clamp 0–100, renormalize weights across present components, then subtract the earnings event
penalty (live only) as before.

> Every weight above is a **starting prior**, logged in `config.py` with a one-line rationale comment.
> The IC report measures whether they hold on live data; adjust gently over time, never curve-fit in one pass.

---

## Versioning & comparability
- `model_version = "v0.2_fundamentals_added"`.
- v0.1 snapshots are preserved untouched. v0.2 runs append new rows under the new version string.
- The performance report must be able to show v0.1 vs v0.2 **side-by-side on the same dates** so you can see
  whether the added factors and reweighting actually improved IC / hit-rate separation — not just assert it.
- Because fundamentals don't backfill, the honest v0.1-vs-v0.2 comparison accrues on **live** data going
  forward. Backfilled v0.2 rows ≈ v0.1 (price/volume only) and should be labeled as such.

---

## Regime-vigilance (the "stay relevant" requirement)
Add to the performance report: for each component, show IC computed on **recent** snapshots (e.g. trailing
~60 live trading days) alongside full-history IC. A factor whose recent IC has decayed materially vs its
full-history IC is an early regime-shift warning. This is how warhorse stays a tool for the present, not
just an accurate reading of the past. (Meaningful only after enough live data accrues — wire it now, it
populates over time.)

---

## Validation additions
- Test that a ticker missing all fundamentals still produces a valid renormalized price/volume score.
- Test that negative P/E is treated as missing, not as "cheap."
- Test that weights renormalize to sum to 1 when components sit out.
- Warn (don't crash) if >40% of the universe is missing a given fundamental field on a run — signals a
  data-source problem worth knowing about.
- Preserve all existing v0.1 tests; 38/38 must still pass.

## Build order
1. `data.py` fundamental + short-interest fetch/cache (throttled, cached, fail-soft).
2. `features.py` new raw features + missing-data flags.
3. `scoring.py` new percentiles, components, sit-out renormalization, reweighted horizon scores from config.
4. Regime-vigilance recent-vs-full IC in `evaluation.py` / report.
5. Tests. Then live run + side-by-side report vs v0.1.

Build in plan mode first. Flag ambiguity before coding. Do not alter v0.1 logic or stored values.
