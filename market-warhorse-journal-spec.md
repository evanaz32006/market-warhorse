# market-warhorse — Daily Journal + AI Brief Spec
## (builds on v0.2; presentation/logging layer — must not alter scoring, evaluation, or storage values)

## Purpose
Give the system a durable daily memory and a legible voice. Two pieces, built in this order in one session:
1. **Journal** — machine-appended structured log of what the system did and found each run.
2. **AI brief (optional add-on)** — a short plain-English summary of the day's journal entry, generated via
   the Anthropic API and embedded in the entry. A LENS on the tool, not a signal — it adds zero edge and
   must never introduce recommendations beyond what the data says.

## Part 1 — Journal (`journal.py`, output to `output/DAILY_LOG.md` + a `journal` table in SQLite)

After every completed run (live or backfill), append one dated entry containing:
- **Run metadata:** run_date, model_version, live-vs-backfill, runtime, tickers scored, fetch summary
  (fresh / cached / FAILED with names), any validation warnings raised.
- **Rankings movement:** today's top 10 by score_20d; names that entered/exited the top 10 vs the previous
  live run; biggest single-day score movers (±).
- **Evaluation state:** per horizon — evaluable snapshot count, Strong-vs-Weak hit rates; per component —
  full-history IC and recent-window IC side by side (the drift columns from v0.2), flagging any component
  whose recent IC has moved materially vs full-history.
- **v0.2 live-validation tracker:** number of live trading days accumulated since v0.2 deploy, and the
  live-only IC of value / quality / short_interest components so far (these have no backfill — this section
  is the whole point of the journal).
- Write the same entry as a structured row (JSON blob is fine) in a `journal` SQLite table so future
  tooling can query history, with DAILY_LOG.md as the human-readable mirror.
- Idempotent: re-running the same run_date replaces that date's entry, never duplicates.

## Part 2 — AI brief (`brief.py`)
- After the journal entry is written, if an Anthropic API key is available (env var `ANTHROPIC_API_KEY`),
  send the day's structured journal data to the Claude API (model: claude-sonnet-4-6, a few hundred
  tokens out) with a system prompt along these lines:
  "You are the daily analyst for a self-evaluating stock-ranking research system. Summarize today's run
  in under 200 words of plain English for the owner: what ran, anything that failed or warrants attention,
  how the live validation of the v0.2 fundamental factors is progressing, and any notable IC drift.
  Be factual and unhyped. This is a research instrument; never phrase anything as a buy/sell recommendation."
- Embed the returned text at the top of that day's DAILY_LOG.md entry under "**Brief:**".
- **Graceful degradation is mandatory:** no API key → skip silently with a one-line note ("brief skipped —
  no API key"); API error/timeout → journal entry still completes, error logged, run never fails because
  the brief failed. The journal must never depend on the brief.
- Add cost guard: one brief per run_date maximum (idempotent with the journal entry replacement).

## Wiring
- `app.py` calls journal (and then brief) as the final step of every run, after display.
- No changes to scoring.py / evaluation.py / storage.py values. Read-only consumers of existing outputs
  plus the new journal table.
- Tests: journal entry completeness on a synthetic run; idempotency (same date twice → one entry);
  brief skip path with no key; brief failure path leaves journal intact. All existing tests stay green.

## Explicitly out of scope
- No recommendations, no trade language in the brief.
- No AI analysis of individual stocks (that's a future, separate layer).
- No scheduling logic in code — the OS Task Scheduler owns timing.
