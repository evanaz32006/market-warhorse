# RUNBOOK — operating market-warhorse alone

*Written 2026-09-10. This is the "everything else is gone, what do I actually do" document.*
*It assumes no memory of how any of this was built.*

---

## The one-minute version

The system runs itself nightly. You do not need to do anything for it to keep working.

Once a day, run this and read one line:

```
python app.py --status
```

- `[status] OK` → nothing to do.
- `[status] STALE` or an error → see **When it breaks** below.

Once a week, run this:

```
python app.py --backup D:\warhorse_backups
```

That is the whole maintenance burden.

---

## What runs on its own

A Windows Task Scheduler job named **"Warhorse Daily Run"** executes `python app.py` each night.
It fetches prices, scores the universe, writes a snapshot per ticker, evaluates past predictions
whose horizons have matured, and appends to `output/DAILY_LOG.md`.

It is **self-healing**: if the machine was off, the next run detects the missed trading days and
reconstructs them. You do not backfill by hand.

> Editing that scheduled task requires an **elevated** (Administrator) terminal. Without elevation
> the edit appears to succeed and silently does nothing.

---

## What to look at

| File | What it tells you |
|---|---|
| `output/DAILY_LOG.md` | The machine's own daily write-up. Start here. |
| `output/latest_rankings.csv` | Today's ranked universe. |
| `output/performance_review.csv` | **Whether the model actually works** — IC and hit rate per component per horizon. |
| `output/research/*.csv` | Results of opt-in research runs (see below). Never written by the nightly job. |

### Reading `performance_review.csv` without fooling yourself

Three columns decide whether a row means anything:

- **`ic_mean`** — rank correlation between the score and what happened next. In this field, 0.02
  is weak, 0.05 is decent, 0.10 is strong. It is **not** a win rate.
- **`overlap_adjusted_t`** — the t-statistic corrected for the fact that daily snapshots of a
  120-day return overlap almost completely. Below about 2, the number is not distinguishable from
  luck.
- **`effective_independent_n`** — how many genuinely independent observations are behind the row.
  At a 120-day horizon over two years this is roughly **3**. A conclusion drawn from 3 observations
  is a hint, not a fact.

**If a short horizon (5d) suddenly shows strong signal, suspect a bug before believing it.**
Published research says signal should grow with horizon. An inverted pattern has historically meant
a date-join error in this codebase, not a discovery.

---

## Commands

```
python app.py                      # the nightly run (Task Scheduler does this for you)
python app.py --status             # health + staleness verdict. The one you actually use.
python app.py --top 30             # show more rows in the terminal display
python app.py --backup <DEST_DIR>  # verified database snapshot. Do this weekly.
pytest tests/ -q                   # 245 tests. Run after ANY code change.
```

Research analyses — **opt-in, report only, never on the nightly path**. Each takes minutes and
writes to `output/research/`:

```
python app.py --research decay         # where signal peaks by horizon
python app.py --research backtest      # simulated account with real costs
python app.py --research patterns      # conditional pattern tests ("after X, does Y happen?")
python app.py --research insider       # SEC Form 4 insider buying vs forward returns
python app.py --research walkforward   # out-of-sample weight fitting
python app.py --ingest-insider         # refresh SEC insider datasets (cached, idempotent)
```

---

## When it breaks

### `--status` says STALE

1. Is it a weekend or market holiday? Then it is correct — there was no session. Entries key on
   **trading date**, so nothing updates on a non-trading day.
2. Otherwise just run `python app.py`. The recovery logic reconstructs missed days.

### `database is locked`

Something else is reading the database — a research run, an open DB browser, a second `app.py`.
Close it and retry. The database is in WAL mode with a busy timeout, so this should be rare; it is
almost always two writers.

### yfinance errors / rate limiting

Yahoo allows roughly 360 requests an hour. A failed ticker is logged and skipped, never fatal. If
many fail, wait an hour and re-run. Do not loop retries — that is how an IP gets blocked.

### Tests fail after a change

Revert the change. `git log --oneline` then `git checkout <commit> -- <file>`. The tests are written
as adversarial claims about specific bugs; a failure usually means a real defect was reintroduced,
not that a test is stale.

---

## The things that will bite you

1. **`data/market_data.db` is 14.1 GB and PARTIALLY IRREPLACEABLE.** `fetch_period` is 2 years, so
   Yahoo no longer serves bars older than the rolling two-year window, while this file holds history
   back to 2024-06-24. **That older window exists in exactly one place.** If the file is lost, no
   past model version can ever be reproduced. It is excluded from git deliberately — 14 GB does not
   belong in a repository — which means **the backup command is the only protection it has.**

2. **Never edit a past snapshot.** `model_version` is part of the key. New logic means a new version
   string running side by side, never a rewrite of history. Five versions exist and all are frozen.

3. **Never let a feature see the future.** Anything computed "as of" date D uses only data up to and
   including D. Forward returns join on real trading dates within each ticker's own series. EDGAR
   fundamentals and insider filings gate on `filed_date <= D`, not on the date the quarter ended or
   the trade happened. A violation here produces a beautiful backtest and no error message.

4. **Missing data is `null` plus a flag, never a zero.** A stretch with no insider buying and a
   stretch with no insider DATA are different facts. Writing both as 0 turns a data gap into a
   signal.

5. **Every tunable number lives in `src/config.py`.** If you find yourself typing a threshold
   anywhere else, it belongs there instead.

---

## What this system is and is not

It is a **measurement instrument**. It ranks stocks and then grades its own past rankings.

It places no trades and connects to no broker, by design.

Its own output says it does **not** beat a passive index fund on return — eight of nine simulated
configurations lost to buying and holding SPY. It wins on risk-adjusted terms (Sharpe 1.53 vs 1.10),
which is a weaker and different claim. Every historical number is inflated by survivorship bias,
which is why every backtest row is stamped `survivorship_biased=True`.

Believe the negative results. They were the point.

---

## Where the detail lives

| File | Contents |
|---|---|
| `CLAUDE.md` | The invariants. Read this before changing anything. |
| `SESSION_STATE.md` | Engineering log — every bug found, and the reasoning behind each fix. |
| `ROADMAP.md` | Decisions and standing disciplines. |
| `NEXT_STEPS.md` | What was planned next and why. |
| `PROJECT_DEBRIEF.md` | Self-contained summary of the whole project. |
