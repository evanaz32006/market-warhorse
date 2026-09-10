# market-warhorse — Daily Log Redesign Spec

Read CLAUDE.md and ROADMAP.md first. Redesign the daily log entry (DAILY_LOG.md + journal table)
to have exactly four sections per day. This is presentation/journal only — no changes to scoring
or evaluation values. Plan mode first.

---

## 1. Today's Rankings

Top 10 by score_20d (current model version): ticker, sector, score_20d, label, days_until_earnings.
Below the table: names that ENTERED and EXITED the top 10 vs the previous live run.
Header keeps the standing line: "research ranking, NOT a buy recommendation."

## 2. Predictions that came due today

A snapshot made on date D becomes gradable at horizon N once N trading days have elapsed
(D+5, D+20, D+60, D+120 in TRADING days, resolved against actual dates in price_history —
never row counts).

Each daily entry grades every cohort that matured TODAY:
- Once ≥5 live trading days exist, every entry grades the 5d cohort from 5 trading days prior.
- Once ≥20 live trading days exist, each entry ALSO grades that day's maturing 20d cohort.
- Same pattern at 60 and 120: past those marks, multiple cohorts graduate every single day
  (rolling conveyor: one day in, one day out).

For each maturing cohort show: snapshot date, horizon, n, Strong-bucket hit rate vs Weak-bucket
hit rate (hit = beat assigned benchmark over the window). Label small-n cohorts low-confidence.
A cohort is graded exactly once — on the day it matures. Historical graded cohorts live in the
journal table; do not re-print them in later daily entries.

## 3. Running scoreboard

Cumulative Strong-vs-Weak hit rates per horizon across ALL live (non-backfill) snapshots to date,
shown alongside the backfill-era numbers for comparison. Cumulative view only — this section is
the "is the IC working" answer, and it must aggregate, not react day-by-day.

## 4. Live validation tracker (two distinct jobs — keep them visually separate)

**4a. New-factor live IC accumulation:** live trading days accumulated since v0.2 deploy, and the
live-only IC (with n) for value_component, quality_component, and short_interest_component.
These have NO backfill — this subsection is the running answer to "are the fundamental factors
earning their weight." If n is too small to be meaningful, say "too early (n=X)" rather than
printing a misleading number.

**4b. Drift flags on established components:** for components that DO have backfill history
(trend, momentum, relative strength, risk, volume, setup, market regime), compare recent-window
IC (trailing ~60 live trading days) against full-history IC. Flag any component whose recent IC
has moved materially from its full-history value (e.g. |recent − full| ≥ 0.05 once recent-window
n is sufficient; threshold lives in config.py). Until enough live days exist, print
"too early — accruing" rather than fake flags.

---

Entries remain append-only and idempotent per run_date. All existing tests stay green; add tests
for cohort-maturity date logic (trading days, not calendar/row counts), grade-once behavior,
and the 4a/4b too-early paths.
