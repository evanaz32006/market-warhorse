# CLAUDE.md — market-warhorse

## What this project is
A stats-only, self-evaluating swing-trade **research and ranking** system. It ranks a watchlist across
multiple horizons, snapshots scores daily, and measures whether high scores actually predicted
outperformance vs a benchmark. It is a **measurement instrument and a chassis for richer data later** —
NOT a trade signal, NOT a money-maker on its own. Treat every parameter as a testable default, not a fact.

## Absolute invariants (never violate)
1. **NO LOOKAHEAD.** Any feature or score computed "as of" date D uses ONLY data up to and including D.
   This is the single most important rule. A lookahead leak produces a beautiful, false backtest.
2. **Never invent data.** Missing → `null` plus an explicit `*_missing` flag. No interpolation of prices,
   no guessed earnings dates, no forward-fill across gaps that fabricates values.
3. **All tunable numbers live in `config.py`** in a single `PARAMS` (and weight) dict. Do NOT hardcode
   thresholds, weights, or window lengths anywhere else. They must be auditable in one place.
4. **Stats only.** No broker connection, no order placement, no buy/sell commands, no position sizing.
5. **Versioned history is immutable.** `model_version` is part of the snapshot key. Never overwrite or
   silently mutate past snapshots; new logic = new version string, run side-by-side.

## Evaluation correctness (where bugs hide)
- Forward returns are computed from ACTUAL price history joined by **real trading date**, never by row
  position / run count in the snapshot table. `shift(-N)` across a mixed-ticker frame by row order is a bug.
- Always resolve forward dates within each ticker's own date-sorted series (`groupby(ticker)`). One
  ticker's rows must never bleed into another's.
- Guardrail: exclude a snapshot from a horizon's metrics if D+N hasn't elapsed yet in real price history.

## Sanity check (use as a correctness test, not just analysis)
Published priors say momentum / relative-strength / 52-week-high components should carry the predictive
signal; setup-flag and 1–5 day "short momentum" components should be near zero or negative (short-horizon
returns mean-revert). When the first `performance_review.csv` lands:
- If momentum/RS/52wh show positive IC → harness is probably wired correctly.
- If setup flags or short-momentum dominate, or signs are inverted → SUSPECT A LOOKAHEAD OR DATE-JOIN BUG
  before believing the result. Investigate the pipeline, don't celebrate the numbers.

## yfinance reliability (mandatory)
Yahoo's endpoints enforce ~360 requests/hour and rate-limit/IP-block on heavy use.
- Batch downloads (5–10 tickers/call), configurable delay between batches.
- Retry-with-exponential-backoff on `YFRateLimitError` and generic errors; a failed ticker logs and is
  skipped, never crashes the run.
- Cache OHLCV to SQLite (`price_history`); on later runs fetch only incremental missing dates.
- Pin yfinance in `requirements.txt`.

## Build order (do not build all seven src files at once)
Plan and build in stages; validate before proceeding:
1. `data.py` + `storage.py` + `features.py` → prove ONE ticker computes end-to-end with no-lookahead.
2. `scoring.py` (percentiles, components, horizon scores).
3. `evaluation.py` + backfill mode.
Run and inspect output after each stage.

## Working agreement
- If reality doesn't match the plan during execution, STOP and return to plan mode. Do not silently
  improvise a workaround — surface it.
- Prefer small, single-purpose, heavily-commented functions over clever density. This code must stay
  auditable by a non-expert owner.
- When you discover a wrong assumption, capture the correction here in CLAUDE.md so it isn't repeated.

## Extensibility (the real roadmap)
The edge comes from richer DATA added later (estimate revisions, fundamentals, options, text-derived
features), not from these price/volume stats. Design so a new signal = a new feature column + new weights
in `config.py` + a bumped `model_version`. Never break the snapshot schema's backward comparability.
