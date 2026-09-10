"""market-warhorse — daily run and backfill entry point.

Loads the watchlist, fetches/caches OHLCV, computes raw features + cross-sectional
percentiles + component scores + horizon scores for every ticker with a fresh bar, saves
a snapshot per ticker, exports CSVs, and runs the self-evaluation loop. Stats/research
only — no trade signals, no broker connection.

    python app.py --backfill   # once, to bootstrap point-in-time history
    python app.py              # daily — appends one fresh live snapshot per ticker
"""

import argparse
import inspect
import json
import os
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from src import brief, data, display, evaluation, features, journal, scoring, storage, universe, utils
from src.config import (
    EDGAR_MODEL_VERSION,
    EXPANDED_MODEL_VERSION,
    ETF_SECTOR_LABEL,
    FUNDAMENTAL_FIELDS,
    PARAMS,
    SECTOR_NEUTRAL_COMPOSITES,
    SECTOR_NORMALIZE,
)

WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "watchlist.csv")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def _days_until(earnings_date):
    """Days from today to an earnings date, accepting a date, a datetime, or an ISO string.

    The ISO-string case matters: earnings dates now arrive from the `earnings_dates` cache table as
    text rather than as live yfinance objects. Without it every date would fail the isinstance check
    and return None, silently disabling the earnings penalty for the entire universe — a regression
    that changes scores while looking like nothing happened."""
    if earnings_date is None:
        return None
    d = earnings_date.date() if hasattr(earnings_date, "date") else earnings_date
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return None
    if not isinstance(d, date):
        return None
    return (d - date.today()).days


def _normalize_sector(raw_sector):
    """Map a watchlist `sector` label to its GICS group for v0.3 within-sector ranking. The few
    fragmented labels from the original hand-assigned rows collapse via config.SECTOR_NORMALIZE
    (e.g. 'Healthcare' -> 'Health Care'); anything else passes through unchanged. ETFs carry the
    'Index' label, which is left as-is so they can be excluded downstream."""
    if raw_sector is None or (isinstance(raw_sector, float) and pd.isna(raw_sector)):
        return None
    return SECTOR_NORMALIZE.get(raw_sector, raw_sector)


def _warn_sparse_fundamentals(features_by_ticker):
    """Warn (never crash) if more than the configured fraction of the scored universe is
    missing a given fundamental field on a live run — an early sign of a data-source problem.
    Only meaningful on live runs (every backfill row is 100% missing by design)."""
    n = len(features_by_ticker)
    if n == 0:
        return
    threshold = PARAMS["fundamental_sparse_warn_pct"]
    for field in FUNDAMENTAL_FIELDS:
        missing = sum(1 for feat in features_by_ticker.values() if feat.get(field) is None)
        frac = missing / n
        if frac > threshold:
            print(f"[app] WARNING: fundamental field '{field}' missing for {missing}/{n} "
                  f"({frac:.0%}) of the scored universe — check the data source.")


def _call_get_fundamentals(fn, ticker, feat):
    """Call a fundamentals provider that may take (ticker) or (ticker, feat).

    The live yfinance path only needs a ticker; the EDGAR resolver also needs that day's close to
    build market-cap ratios. Supporting both keeps every existing caller (and its tests) working
    unchanged rather than forcing a signature change through the whole codebase.

    The arity is INSPECTED rather than discovered by catching TypeError: a TypeError raised from
    INSIDE a two-arg provider would otherwise be silently swallowed and retried with one argument,
    turning a real bug into mysteriously-missing fundamentals."""
    try:
        n_params = len(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        n_params = 1                      # un-introspectable callable: assume the legacy signature
    return fn(ticker, feat) if n_params >= 2 else fn(ticker)


def run_scoring_for_date(run_date, included, histories, db_path, backfilled, get_earnings,
                         get_fundamentals=None, recovered=False, fundamentals_as_of=None,
                         model_version=None, fundamentals_pit=False):
    """included: list of (ticker, benchmark, sector) tuples already filtered to those with
    a real bar on run_date for both ticker and benchmark. Computes features -> percentiles
    -> components -> horizon scores, upserts one snapshot per ticker, and returns the rows
    needed for the printed ranked table. Shared by both the live path and the backfill loop
    so the two never drift out of sync with each other.

    get_fundamentals(ticker) -> raw fundamentals dict for the live path; defaults to a function
    returning {} so backfill rows carry NO fundamentals (they can't be reconstructed
    historically) — every fundamental field is then None and value/quality/short components sit
    out, leaving a valid price/volume-only score under the v0.2 weights."""
    get_fundamentals = get_fundamentals or (lambda _ticker, _feat=None: {})
    model_version = model_version or PARAMS["model_version"]

    features_by_ticker = {}
    for ticker, benchmark, _sector in included:
        feat = features.compute_features(
            ticker, benchmark, run_date, histories[ticker], histories[benchmark]
        )
        # Merge live fundamentals (or all-None on backfill) into the same feature dict so the
        # cross-sectional composites in compute_percentiles can see them. `feat` is passed through
        # because the EDGAR resolver needs the AS-OF CLOSE (feat["latest_close"]) to build the
        # price-based ratios — its market cap is that day's price x shares from the filings, never
        # today's price against a historical share count.
        feat.update(features.compute_fundamental_features(_call_get_fundamentals(get_fundamentals,
                                                                                 ticker, feat)))
        features_by_ticker[ticker] = feat

    if not backfilled:
        _warn_sparse_fundamentals(features_by_ticker)

    # v0.3 sector-neutral inputs: normalize each ticker's sector to GICS and identify the
    # benchmark ETFs (normalized sector == ETF label) to exclude from value/quality ranking.
    # scoring.compute_percentiles ignores these when SECTOR_NEUTRAL_COMPOSITES is empty, so this
    # is a no-op under v0.1/v0.2 config.
    sector_by_ticker = {t: _normalize_sector(sec) for t, _b, sec in included}
    exclude_tickers = {t for t, sec in sector_by_ticker.items() if sec == ETF_SECTOR_LABEL}

    percentiles_by_ticker = scoring.compute_percentiles(
        features_by_ticker,
        sector_by_ticker=sector_by_ticker,
        sector_neutral_composites=SECTOR_NEUTRAL_COMPOSITES,
        exclude_tickers=exclude_tickers,
        min_sector_size=PARAMS["sector_min_tickers_for_neutral"],
    )

    rows_for_table = []
    snapshot_rows = []          # collected and written in ONE transaction — see the batch write below
    for ticker, benchmark, sector in included:
        feat = features_by_ticker[ticker]
        pct = percentiles_by_ticker[ticker]

        earnings_date, earnings_missing = get_earnings(ticker)
        days_until_earnings = _days_until(earnings_date)

        components = scoring.compute_all_components(feat, pct, ticker=ticker)
        horizon_scores = scoring.compute_horizon_scores(
            components, days_until_earnings=days_until_earnings,
            earnings_risk_unknown=earnings_missing, ticker=ticker,
        )

        snapshot_row = dict(feat)
        snapshot_row.update(pct)
        snapshot_row.update(components)
        snapshot_row.update(horizon_scores)
        snapshot_row.update({
            "run_date": run_date,
            "ticker": ticker,
            "benchmark": benchmark,
            "model_version": model_version,
            "backfilled": backfilled,
            # recovered: a LIVE snapshot (backfilled=0) rebuilt point-in-time for a missed day; its
            # fundamentals were stamped from a later fetch (fundamentals_as_of), never point-in-time.
            "recovered": 1 if recovered else 0,
            "fundamentals_as_of": fundamentals_as_of,
            # fundamentals_pit: were the FUNDAMENTALS on this row genuinely as-of run_date? True only
            # for EDGAR-sourced rows (filed_date <= D). This is what the fundamental-factor IC keys
            # off, so a v0.4 recovered day still counts while a v0.3 one does not.
            "fundamentals_pit": 1 if fundamentals_pit else 0,
            "earnings_risk_unknown": earnings_missing,
            "days_until_earnings": days_until_earnings,
            "earnings_date_missing": earnings_missing,
            "timestamp_fetched": datetime.now(timezone.utc).isoformat(),
        })
        snapshot_rows.append(snapshot_row)

        rows_for_table.append({
            "ticker": ticker,
            "sector": sector,
            "score_5d": horizon_scores.get("score_5d"),
            "score_20d": horizon_scores.get("score_20d"),
            "score_60d": horizon_scores.get("score_60d"),
            "score_120d": horizon_scores.get("score_120d"),
            "label_20d": scoring.label_for_score(horizon_scores.get("score_20d")),
            "latest_close": feat.get("latest_close"),
        })

    # ONE transaction for the whole date instead of one commit (an fsync) per ticker. Writing ~500
    # rows individually against a 5 GB database made the v0.4 backfill I/O-bound at 30% CPU and on
    # track for ~24 hours; batching per date is the same SQL with the same idempotency, ~500x fewer
    # fsyncs. Written AFTER the loop so a mid-date failure leaves the date absent rather than
    # half-scored — and the upsert is keyed on (run_date, ticker, model_version), so a re-run
    # overwrites its own partial work cleanly.
    storage.upsert_feature_snapshots(snapshot_rows, db_path=db_path)
    return rows_for_table


def _included_for_date(watchlist, date_sets, run_date):
    """Tickers eligible to be scored as-of run_date: a ticker is included iff it AND its assigned
    benchmark both have a REAL price bar dated exactly run_date (a ticker that IPO'd later simply has
    no row, never an invented one). Returns a list of (ticker, benchmark, sector) tuples. Shared by
    backfill and missed-day recovery so the point-in-time inclusion rule lives in exactly one place."""
    included = []
    for _, row in watchlist.iterrows():
        ticker, benchmark = row["ticker"], row["benchmark"]
        if run_date in date_sets.get(ticker, ()) and run_date in date_sets.get(benchmark, ()):
            included.append((ticker, benchmark, row["sector"]))
    return included


def _run_live(watchlist, histories, latest_dates, db_path):
    run_date = max(latest_dates.values())
    print(f"[app] run_date resolved to most recent available trading day: {run_date}")

    included, skipped = [], []
    for _, row in watchlist.iterrows():
        ticker, benchmark = row["ticker"], row["benchmark"]
        ticker_hist, benchmark_hist = histories.get(ticker), histories.get(benchmark)
        if not ticker_hist or not benchmark_hist:
            skipped.append((ticker, "no cached price history"))
            continue
        if latest_dates.get(ticker) != run_date or latest_dates.get(benchmark) != run_date:
            skipped.append((ticker, f"stale data (latest={latest_dates.get(ticker)}, "
                                     f"benchmark latest={latest_dates.get(benchmark)})"))
            continue
        included.append((ticker, benchmark, row["sector"]))

    if skipped:
        print(f"[app] skipped {len(skipped)} ticker(s) this run:")
        for t, reason in skipped:
            print(f"  - {t}: {reason}")

    if not included:
        print("[app] no tickers had fresh data for this run_date — nothing to score.")
        return None

    # Fundamentals are a LIVE-ONLY factor (point-in-time as of fetch, not backfillable). Fetch
    # them once for the scored tickers, throttled + cached; a failed ticker just sits out.
    scored_tickers = [t for t, _b, _s in included]
    fundamentals_map = data.fetch_fundamentals(scored_tickers, db_path=db_path)
    # Earnings dates are now fetched ONCE for the universe, cached, and refreshed on a rolling slice —
    # they used to be an uncached network call inside the per-ticker scoring loop (one HTTP request per
    # ticker per run). `run_scoring_for_date` still takes a get_earnings callable, so this is a pure
    # source swap: a dict lookup instead of a request.
    earnings_map = data.fetch_earnings_dates(scored_tickers, db_path=db_path)

    run_scoring_for_date(
        run_date, included, histories, db_path, backfilled=False,
        get_earnings=lambda t: earnings_map.get(t, (None, True)),
        get_fundamentals=lambda t: fundamentals_map.get(t) or {},
    )
    # Report the run's own facts back to main() so it can journal them (they're in no CSV). The
    # fundamentals_map + as-of date are handed back so missed-day recovery can reuse this single
    # fetch (most-recent values) rather than re-fetching, stamping recovered rows fundamentals_as_of.
    return {"run_date": run_date, "tickers_scored": len(included), "skipped": skipped,
            "fundamentals_map": fundamentals_map,
            "fundamentals_as_of": date.today().isoformat()}


def _run_backfill(watchlist, histories, db_path):
    """Reconstruct point-in-time scores for every trading date in SPY's cached history
    (it's fetched for every run as the universal benchmark and trades every NYSE
    session, so its date list is the master backfill calendar). A ticker is included on
    date D only if it AND its assigned benchmark both have a real bar dated exactly D —
    tickers that listed later (e.g. ARM, GEV, VST, CEG) simply have no rows before their
    IPO, never invented. Earnings penalty is always skipped (historical days_until_earnings
    is not reconstructable) and earnings_risk_unknown=True / backfilled=True on every row."""
    spy_hist = histories.get("SPY")
    if not spy_hist:
        print("[app] no SPY history cached — cannot determine the backfill calendar, aborting.")
        return None

    run_dates = [row["date"] for row in spy_hist]
    date_sets = {t: {r["date"] for r in h} for t, h in histories.items()}
    no_earnings = lambda ticker: (None, True)

    total = len(run_dates)
    print(f"[app] backfill: reconstructing {total} trading date(s) from {run_dates[0]} "
          f"to {run_dates[-1]} (no network calls — all data already cached)")

    last_scored = None  # (run_date, count) of the most recent date that actually scored anything
    for i, run_date in enumerate(run_dates, start=1):
        included = _included_for_date(watchlist, date_sets, run_date)
        if included:
            run_scoring_for_date(run_date, included, histories, db_path,
                                  backfilled=True, get_earnings=no_earnings)
            last_scored = (run_date, len(included))
        if i % 25 == 0 or i == total:
            print(f"[app] backfill progress: {i}/{total} dates done")

    if last_scored is None:
        return None
    # Journal a single entry keyed on the final backfilled date.
    return {"run_date": last_scored[0], "tickers_scored": last_scored[1], "skipped": []}


def _run_edgar_backfill(watchlist, histories, db_path, model_version=None):
    """Phase 4 of v0.4: reconstruct point-in-time scores WITH fundamentals, under a new model_version.

    The only difference from `_run_backfill` is where fundamentals come from. v0.1-v0.3 backfill rows
    carry none at all (yfinance has no history), so value/quality sit out and a backfilled row is
    effectively price/volume-only. EDGAR publishes each XBRL fact with its FILED date, so for any date
    D we can resolve exactly what a filer had published by then — which finally makes value/quality
    backfillable and therefore validatable on years of data instead of weeks.

    Two no-lookahead guarantees, both structural:
      - the resolver is called with as_of_date=D and only reads facts where filed_date <= D;
      - market-cap ratios use THAT DAY'S close (feat["latest_close"]), never today's price.
    Rows are written with fundamentals_pit=1 — genuinely point-in-time, unlike a v0.3 recovered row.
    """
    from src import edgar

    spy_hist = histories.get("SPY")
    if not spy_hist:
        print("[app] no SPY history cached — cannot determine the backfill calendar, aborting.")
        return None

    run_dates = [row["date"] for row in spy_hist]
    date_sets = {t: {r["date"] for r in h} for t, h in histories.items()}
    no_earnings = lambda ticker: (None, True)
    sector_by_ticker = dict(zip(watchlist["ticker"], watchlist["sector"]))

    total = len(run_dates)
    model_version = model_version or EDGAR_MODEL_VERSION
    print(f"[app] EDGAR backfill ({model_version}): {total} trading date(s) from "
          f"{run_dates[0]} to {run_dates[-1]} — fundamentals resolved point-in-time from filings")

    # One DB read per ticker instead of one per (ticker, date): ~500 queries instead of ~266,000,
    # which is the difference between minutes and a measured 26 hours. The filed-date gate is
    # identical either way (see edgar._facts_as_of).
    print("[app] pre-loading EDGAR facts index...", flush=True)
    facts_index = edgar.build_facts_index(sorted(set(watchlist["ticker"])), db_path=db_path)
    print(f"[app] facts index ready: {sum(len(f) for f, _ in facts_index.values()):,} facts "
          f"across {len(facts_index)} tickers", flush=True)

    # RESUMABLE. A multi-hour backfill that dies partway (a lock, a reboot, a killed session) must
    # not restart from date one. Dates already written for THIS model_version are skipped, mirroring
    # the per-company marker that makes the EDGAR ingest resumable. Rows are keyed on
    # (run_date, ticker, model_version), so a re-run of a completed date would be harmless anyway -
    # this just avoids paying for it again.
    already = set(storage.get_backfilled_dates(model_version, db_path=db_path))
    if already:
        print(f"[app] resuming: {len(already)} date(s) already written for {model_version}")

    last_scored = None
    for i, run_date in enumerate(run_dates, start=1):
        if run_date in already:
            continue
        included = _included_for_date(watchlist, date_sets, run_date)
        if included:
            # closes over run_date so every resolution is gated to this date and no other
            def get_fund(ticker, feat, _d=run_date):
                return edgar.get_fundamentals_as_of(
                    ticker, _d, price=feat.get("latest_close"),
                    sector=_normalize_sector(sector_by_ticker.get(ticker)), db_path=db_path,
                    facts_index=facts_index)

            run_scoring_for_date(run_date, included, histories, db_path,
                                 backfilled=True, get_earnings=no_earnings,
                                 get_fundamentals=get_fund,
                                 model_version=model_version, fundamentals_pit=True)
            last_scored = (run_date, len(included))
        if i % 25 == 0 or i == total:
            print(f"[app] EDGAR backfill progress: {i}/{total} dates done", flush=True)

    if last_scored is None:
        return None
    return {"run_date": last_scored[0], "tickers_scored": last_scored[1], "skipped": []}


def _missing_live_days(calendar, live_dates):
    """Sessions within the live-tracking span that never got a live snapshot — the gap set recovery
    fills. Span = [first live snapshot .. most recent completed session (calendar[-1])]; a hole is any
    calendar session in that span with no live snapshot, INCLUDING holes below the max live date (e.g.
    today ran but yesterday didn't). Bounded below by the first live date so pre-tracking history is
    left to --backfill, never mass-reconstructed. Empty until live tracking has started."""
    live = set(live_dates)
    if not calendar or not live:
        return []
    first_live, target = min(live), calendar[-1]
    return [d for d in calendar if first_live <= d <= target and d not in live]


def _recover_missing_days(watchlist, histories, db_path, fundamentals_map, fundamentals_as_of):
    """Self-healing: reconstruct any LIVE trading day that was MISSED (machine off at run time). A
    missed day is any NYSE session (SPY calendar) within the live-tracking span [first live snapshot
    .. most recent completed session] that has no live snapshot of the current model_version —
    INCLUDING holes below the max live date (e.g. today ran but yesterday didn't). Each is rebuilt
    point-in-time from cached price history via the SAME machinery as backfill (run_scoring_for_date,
    strict no-lookahead on price/volume), but written as a LIVE row (backfilled=0) marked recovered=1.
    Fundamentals can't be fetched as-of a past date, so the most-recent fundamentals are applied and
    stamped fundamentals_as_of (flagged staleness, never silent; excluded from the fundamental-factor
    IC downstream). SCORING ONLY — journaling happens centrally after evaluation so every entry sees
    the full snapshot set. Returns [{run_date, tickers_scored}] for the days recovered (chronological)."""
    model_version = PARAMS["model_version"]
    calendar = storage.get_cached_dates("SPY", db_path=db_path)  # ascending NYSE session calendar
    live_dates = set(storage.get_live_run_dates(model_version, db_path=db_path))
    if not calendar or not live_dates:
        return []  # first-ever tracking uses --backfill; never mass-reconstruct pre-tracking history
    # `target` (calendar[-1]) = latest completed session (data-derived); it's scored by the live run
    # and is already in live_dates by the time recovery runs, so it's naturally excluded.
    missing = _missing_live_days(calendar, live_dates)
    if not missing:
        return []

    date_sets = {t: {r["date"] for r in h} for t, h in histories.items()}
    no_earnings = lambda _t: (None, True)  # historical days_until_earnings is not reconstructable
    get_fund = lambda t: fundamentals_map.get(t) or {}
    print(f"[recover] {len(missing)} missed live trading day(s) to reconstruct: {missing}")
    recovered = []
    for d in missing:  # calendar is ascending -> chronological
        included = _included_for_date(watchlist, date_sets, d)
        if not included:
            print(f"[recover] {d}: no ticker has a real bar — skipping")
            continue
        run_scoring_for_date(d, included, histories, db_path, backfilled=False,
                             get_earnings=no_earnings, get_fundamentals=get_fund,
                             recovered=True, fundamentals_as_of=fundamentals_as_of)
        recovered.append({"run_date": d, "tickers_scored": len(included)})
        print(f"[recover] reconstructed {d} as live+recovered ({len(included)} tickers, "
              f"fundamentals as of {fundamentals_as_of})")
    return recovered


def _journal_recovered_days(recovered, fundamentals_as_of, db_path, sector_map, evaluated_rows=None):
    """Journal each recovered missed day (mode=recovered) in its own run_date slot. Called AFTER
    evaluation so each entry's Sections 2/3 reflect the full snapshot set; chronological order in
    DAILY_LOG.md comes from render_daily_log sorting by run_date. Idempotent per run_date; never
    fatal (a journal failure must not undo a completed recovery)."""
    model_version = PARAMS["model_version"]
    for rec in recovered:
        d = rec["run_date"]
        run_context = {
            "run_date": d, "model_version": model_version,
            "backfilled": False, "recovered": True, "runtime_sec": None,
            "tickers_scored": rec["tickers_scored"],
            "fetch_summary": {"fresh": [], "cached_only": [], "failed": []},
            "fundamentals_summary": f"recovered — fundamentals stamped {fundamentals_as_of} (not point-in-time)",
            "warnings": [f"recovered missed day; fundamentals as of {fundamentals_as_of}, excluded from factor IC"],
            "sector_map": sector_map,
        }
        try:
            journal.run_journal(run_context, db_path=db_path, output_dir=OUTPUT_DIR,
                                evaluated_rows=evaluated_rows)
            print(f"[recover] journaled recovered day {d}")
        except Exception as e:  # a journal failure must not undo the recovered snapshot
            print(f"[recover] journal for {d} failed (non-fatal): {e}")


def _export_csvs(db_path, output_dir, full_history=False):
    """Write score_history.csv (ACTIVE model version only, by default) and latest_rankings.csv.

    `score_history.csv` used to be every row of every model_version, rewritten from scratch on every
    nightly run: already 733 MB across 554k rows, and a v0.5 backfill would take it past 3 GB — a
    multi-gigabyte serialize-and-rewrite every night, for versions that are frozen and can never
    change. The active version is what anyone actually reads; the rest is in the database, which is
    the source of truth. `--export-full-history` still dumps everything on demand."""
    current_version = PARAMS["model_version"]
    rows = storage.load_all_snapshots(db_path,
                                      model_version=None if full_history else current_version)
    if not full_history:
        # LIVE rows only. Exporting the active version alone already cut this file from 771 MB to
        # 24 MB - and then the v0.5 promotion undid it, because v0.5 IS the active version and carries
        # 777,738 BACKFILLED rows, pushing the nightly rewrite to 1,161 MB.
        # Backfilled rows are immutable reconstructions: they never change, they are already in the
        # database (the source of truth), and re-serializing a gigabyte of them every night buys
        # nothing. What belongs in a rolling export is the record of what the model actually predicted
        # in real time.  still dumps everything on demand.
        rows = [r for r in rows if not int(r.get("backfilled") or 0)]
        if not rows:
            # A freshly promoted version has no live rows yet; fall back to everything rather than
            # writing an empty file that reads as data loss.
            rows = storage.load_all_snapshots(db_path, model_version=current_version)
    if not rows and not full_history:
        # No rows for the active version yet (e.g. before its first run) — fall back to everything
        # rather than writing an empty file that looks like data loss.
        rows = storage.load_all_snapshots(db_path)
    if not rows:
        print("[app] no snapshots in DB yet — skipping CSV export.")
        return

    history_df = pd.DataFrame(rows)
    history_path = os.path.join(output_dir, "score_history.csv")
    history_df.to_csv(history_path, index=False)

    # latest_rankings is the current model version's most recent run only, so View 1 never
    # mixes v0.1 and v0.2 rows (v0.1 is preserved in the DB but not re-run).
    version_df = history_df[history_df["model_version"] == current_version]
    if version_df.empty:
        version_df = history_df  # fallback: no rows for the current version yet
    latest_run_date = version_df["run_date"].max()
    latest_df = version_df[version_df["run_date"] == latest_run_date]
    latest_path = os.path.join(output_dir, "latest_rankings.csv")
    latest_df.to_csv(latest_path, index=False)

    scope = ("ALL versions + backfill" if full_history
             else f"model_version={current_version}, LIVE rows only")
    print(f"[app] wrote {len(history_df)} row(s) ({scope}) to {history_path}, "
          f"{len(latest_df)} row(s) for run_date={latest_run_date} "
          f"(model_version={current_version}) to {latest_path}")


def _grow_watchlist_with_indices(watchlist):
    """Merge every configured index's constituents into watchlist.csv, never touching an existing
    hand-assigned row (see src/universe.py). Rewrites the file only when the merge actually added
    rows, to avoid no-op mtime/diff churn on days no index changed.

    v0.5 widened this from the S&P 500 alone to S&P 500 + 400 + 600, so the watchlist now spans
    large, mid and small caps. Each row carries its `size_bucket`, which is what lets the research
    layer ask whether short-horizon signal behaves differently outside the most-watched names."""
    before_n = len(watchlist)
    constituents = universe.fetch_all_constituents()
    merged = universe.build_universe_watchlist(watchlist, constituents)
    added = len(merged) - before_n
    if added > 0:
        merged.to_csv(WATCHLIST_PATH, index=False)
        by_bucket = merged["size_bucket"].value_counts().to_dict() if "size_bucket" in merged else {}
        print(f"[universe] watchlist grown: {before_n} existing + {added} new row(s) = "
              f"{len(merged)} total; buckets={by_bucket}")
    return merged


def _print_benchmark_fetch_report(watchlist, fetch_summary):
    """Reports fetch success/failure specifically for the benchmark ETFs, since a missing
    benchmark silently breaks relative-strength features for every ticker assigned to it."""
    benchmark_etfs = sorted(set(watchlist["benchmark"]) | {"SPY"})
    failed_etfs = [t for t in benchmark_etfs if t in fetch_summary["failed"]]
    ok_etfs = [t for t in benchmark_etfs if t not in fetch_summary["failed"]]
    print(f"[app] benchmark ETF coverage: {len(ok_etfs)}/{len(benchmark_etfs)} ok"
          + (f", FAILED: {failed_etfs}" if failed_etfs else ""))
    total = len(set(watchlist["ticker"]) | set(watchlist["benchmark"]))
    print(f"[app] universe coverage: {total - len(fetch_summary['failed'])}/{total} tickers have usable history")


def main():
    parser = argparse.ArgumentParser(description="market-warhorse daily run / backfill")
    parser.add_argument("--backfill", action="store_true",
                         help="reconstruct point-in-time scores for every cached trading date (run once on setup)")
    parser.add_argument("--top", type=int, default=15,
                         help="number of rows to show in the Today's Top Setups display (default 15)")
    parser.add_argument("--backfill-expanded", action="store_true",
                         help="v0.5: the same EDGAR point-in-time backfill over the EXPANDED "
                              "universe, under model_version=" + EXPANDED_MODEL_VERSION)
    parser.add_argument("--backfill-edgar", action="store_true",
                         help="v0.4 Phase 4: reconstruct point-in-time scores WITH EDGAR-derived "
                              "fundamentals under model_version=" + EDGAR_MODEL_VERSION)
    parser.add_argument("--research", choices=["decay", "walkforward", "quality", "shorthorizon", "backtest",
                                  "sizedecay", "patterns", "insider", "events", "all"],
                         help="run an opt-in RESEARCH analysis (report only — changes no score, "
                              "weight or model_version) and exit, never on the nightly path")
    parser.add_argument("--backup", nargs="?", const="", metavar="DEST_DIR",
                         help="write a VERIFIED, consistent snapshot of the database (VACUUM INTO, "
                              "integrity-checked and row-count-matched) and exit. Give a path on "
                              "ANOTHER physical device; omit it to use PARAMS['backup_dir']")
    parser.add_argument("--ingest-filings", action="store_true",
                         help="fetch the SEC filing index (8-K item codes, 10-K/10-Q dates) for the "
                              "universe via the submissions API; idempotent per accession")
    parser.add_argument("--ingest-insider", action="store_true",
                         help="download and ingest SEC quarterly Form 3/4/5 insider datasets "
                              "(cached on disk; idempotent per quarter)")
    parser.add_argument("--research-version", default=None,
                         help="model_version for --research (default: config PARAMS model_version)")
    parser.add_argument("--status", action="store_true",
                         help="print the last-successful-run health record and a staleness verdict, "
                              "then exit (trustworthy alternative to Task Scheduler's Last Result)")
    args = parser.parse_args()

    start_time = time.time()
    db_path = storage.DEFAULT_DB_PATH
    storage.init_db(db_path)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.status:
        _print_status(db_path)
        return

    if args.backup is not None:
        from src import backup
        dest = args.backup or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           *PARAMS["backup_dir"].split("/"))
        backup.backup_database(dest, db_path=db_path)
        return

    if args.ingest_filings:
        from src import filings
        filings.ingest_filings(db_path=db_path)
        return

    if args.ingest_insider:
        from src import insider
        insider.ingest_insider_quarters(db_path=db_path)
        return

    # Research analyses return BEFORE any fetching or scoring: a structural guarantee that a
    # minute-scale analysis can never run as part of the nightly job.
    if args.research:
        from src import research
        version = args.research_version or PARAMS["model_version"]
        if args.research in ("decay", "all"):
            research.run_decay_analysis(db_path=db_path, model_version=version)
        if args.research in ("walkforward", "all"):
            research.run_walk_forward_analysis(db_path=db_path, model_version=version)
        if args.research in ("quality", "all"):
            research.run_quality_decomposition(db_path=db_path, model_version=version)
        if args.research in ("shorthorizon", "all"):
            research.run_short_horizon_research(db_path=db_path, model_version=version)
        if args.research in ("sizedecay", "all"):
            research.run_size_bucket_decay(db_path=db_path, model_version=version)
        if args.research in ("backtest", "all"):
            from src import backtest
            backtest.run_portfolio_backtest(db_path=db_path, model_version=version)
        if args.research in ("events", "all"):
            research.run_event_research(db_path=db_path, model_version=version)
        if args.research in ("insider", "all"):
            research.run_insider_research(db_path=db_path, model_version=version)
        if args.research in ("patterns", "all"):
            # Deliberately takes no model_version: the pattern harness reads PRICE HISTORY only,
            # never `feature_snapshots`, so it is unaffected by which model is live and its
            # results do not need re-running when a version is promoted.
            from src import patterns
            patterns.run_pattern_research(db_path=db_path)
        return

    watchlist = pd.read_csv(WATCHLIST_PATH)
    watchlist = _grow_watchlist_with_indices(watchlist)
    all_tickers = sorted(set(watchlist["ticker"]) | set(watchlist["benchmark"]))

    fetch_summary = data.fetch_price_history(all_tickers, db_path=db_path)
    print(f"[app] fetch summary: {fetch_summary}")
    _print_benchmark_fetch_report(watchlist, fetch_summary)

    histories = {t: storage.load_price_history(t, db_path=db_path) for t in all_tickers}
    utils.check_duplicate_price_rows(histories)
    utils.check_benchmark_coverage(watchlist, histories)
    for t in all_tickers:
        if histories.get(t):
            utils.check_sufficient_history(t, histories[t])

    latest_dates = {t: h[-1]["date"] for t, h in histories.items() if h}
    if not latest_dates:
        print("[app] no price history available for any ticker — aborting run.")
        return

    recovered = []
    if args.backfill_expanded:
        run_result = _run_edgar_backfill(watchlist, histories, db_path,
                                         model_version=EXPANDED_MODEL_VERSION)
    elif args.backfill_edgar:
        run_result = _run_edgar_backfill(watchlist, histories, db_path)
    elif args.backfill:
        run_result = _run_backfill(watchlist, histories, db_path)
    else:
        run_result = _run_live(watchlist, histories, latest_dates, db_path)
        # Self-healing: reconstruct any missed live trading days BEFORE evaluation, reusing this
        # run's single fundamentals fetch, so today's scoreboard already reflects them.
        if run_result:
            recovered = _recover_missing_days(
                watchlist, histories, db_path,
                fundamentals_map=run_result.get("fundamentals_map") or {},
                fundamentals_as_of=run_result.get("fundamentals_as_of"),
            )

    _export_csvs(db_path, OUTPUT_DIR)
    # ONE forward-return evaluation pass per run: run_evaluation writes performance_review.csv AND hands
    # back the evaluated rows (all versions) so the journal reuses them instead of recomputing the whole
    # join again — and again for every recovered day.
    _review_df, evaluated_rows = evaluation.run_evaluation(
        db_path=db_path, output_dir=OUTPUT_DIR, return_rows=True)

    display.print_top_setups(
        os.path.join(OUTPUT_DIR, "latest_rankings.csv"), WATCHLIST_PATH, top_n=args.top
    )
    display.print_performance_summary(os.path.join(OUTPUT_DIR, "performance_review.csv"))

    # {ticker: sector} for the journal's Section 1 (sector isn't stored in feature_snapshots).
    sector_map = dict(zip(watchlist["ticker"], watchlist["sector"]))
    # Journal recovered missed days first (after evaluation, so their scoreboards are complete), then
    # today's entry. Chronological order in the log comes from render_daily_log sorting by run_date.
    _journal_recovered_days(
        recovered, run_result.get("fundamentals_as_of") if run_result else None,
        db_path, sector_map, evaluated_rows,
    )
    _run_journal_and_brief(run_result, args.backfill, fetch_summary, start_time, db_path,
                           sector_map, evaluated_rows)

    # Trustworthy health sentinel — written ONLY here, at a clean end of the pipeline. `--status`
    # reads it instead of Task Scheduler's Last Result, which is often 0x8007042B (process aborted)
    # when the machine shuts down at exit even though the day's work completed and persisted.
    _record_run_success(run_result, recovered, db_path)


def _record_run_success(run_result, recovered, db_path):
    """Record that the pipeline completed cleanly, with what it produced. Best-effort (a sentinel
    failure must not fail an otherwise-successful run)."""
    try:
        storage.set_meta("last_success", json.dumps({
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "run_date": run_result.get("run_date") if run_result else None,
            "model_version": PARAMS["model_version"],
            "tickers_scored": run_result.get("tickers_scored") if run_result else 0,
            "recovered_days": [r["run_date"] for r in (recovered or [])],
        }), db_path=db_path)
    except Exception as e:
        print(f"[app] could not write last_success sentinel (non-fatal): {e}")


def weekdays_between(start_date, end_date):
    """Count of weekdays strictly after `start_date` and strictly before `end_date`.

    Wall-clock, deliberately — NOT derived from cached prices. See `_print_status` for why that
    distinction is the whole point. Market holidays are not subtracted (no exchange calendar is
    available offline), so this can OVERCOUNT by one on a holiday week. That error is in the safe
    direction: a spurious "check this" beats a confident "all fine"."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    n, cur = 0, start + timedelta(days=1)
    while cur < end:
        if cur.weekday() < 5:
            n += 1
        cur += timedelta(days=1)
    return n


def thin_live_days(counts, min_fraction=None, lookback=None):
    """Live days whose scored-ticker count is materially below the trailing norm.

    Recovery ([`_missing_live_days`](app.py)) only finds sessions with ZERO snapshots. A session
    that scored 945 of 1,521 names is "present" by that test and is never revisited — yet its
    sector-neutral percentile ranks were computed on 62% of the universe, which is a silently wrong
    ranking rather than a missing one. Observed live on 2026-09-10.

    The norm is the MEDIAN of the preceding `lookback` sessions, not the mean: one thin day would
    drag a mean down and help the next thin day pass. Days with too little history behind them to
    judge are left alone rather than guessed at.

    `counts`: [(run_date, n)] ascending. Returns [(run_date, n, expected)] worst-first."""
    min_fraction = min_fraction if min_fraction is not None else PARAMS["min_live_coverage_fraction"]
    lookback = lookback if lookback is not None else PARAMS["live_coverage_lookback_days"]
    out = []
    for i, (run_date, n) in enumerate(counts):
        prior = [c for _, c in counts[max(0, i - lookback):i]]
        if len(prior) < 5:
            continue                      # not enough history to call anything abnormal
        expected = sorted(prior)[len(prior) // 2]
        if expected and n < expected * min_fraction:
            out.append((run_date, n, expected))
    return sorted(out, key=lambda r: r[1] / float(r[2]))


def _print_status(db_path, today=None):
    """Print the last successful run and whether the log is current.

    Reports TWO independent checks, because the obvious one cannot see the failure that matters.

    The cached-data check compares the last good `run_date` against `latest_trading_date`, which is
    MAX(date) from `price_history`. That is circular: if the nightly run never completed, no new bar
    was fetched, so the "latest session" is still the last one we already have, it equals the last
    good run_date, and the check reports OK. A whole missed session is invisible to it — verified on
    2026-09-09, when the run was killed 2 minutes in and `--status` still said OK the next day.

    So the second check uses the WALL CLOCK: how many weekdays have passed since the last good run.
    If a weekday has gone by AND no new price data arrived, the cache is stale too, and the honest
    verdict is "something did not run" rather than "up to date"."""
    raw = storage.get_meta("last_success", db_path=db_path)
    if not raw:
        print("[status] no successful run recorded yet.")
        return
    rec = json.loads(raw)
    last_rd, latest = rec.get("run_date"), storage.latest_trading_date(db_path=db_path)
    print(f"[status] last success: run_date={last_rd} · model={rec.get('model_version')} · "
          f"finished={rec.get('finished_at')} · tickers={rec.get('tickers_scored')} · "
          f"recovered_days={rec.get('recovered_days')}")

    today = today or date.today().isoformat()
    missed = weekdays_between(last_rd, today) if last_rd else 0

    if latest is not None and last_rd != latest:
        print(f"[status] STALE — last good run was {last_rd}, latest session is {latest}. "
              f"Next run (or recovery) will catch up.")
    elif missed >= 1:
        print(f"[status] SUSPECT — {missed} weekday(s) have passed since {last_rd} and NO new "
              f"price data arrived either. That means the nightly run did not complete, not that "
              f"the market was quiet. (A weekday market holiday is the benign explanation.)")
        print(f"[status] Fix: run `python app.py` — recovery reconstructs missed sessions. "
              f"Then check Task Scheduler's Last Run Result for 'Warhorse Daily Run'.")
    else:
        print(f"[status] OK — up to date with the latest trading session ({latest}).")

    # Coverage is a SEPARATE question from freshness. A day can be present and current while having
    # scored two thirds of the universe.
    thin = thin_live_days(storage.live_snapshot_counts(PARAMS["model_version"], db_path=db_path))
    recent = [t for t in thin if not last_rd or t[0] >= _n_sessions_back(db_path, 30)]
    if recent:
        print(f"[status] INCOMPLETE COVERAGE — {len(recent)} recent session(s) scored well "
              f"below the norm; their cross-sectional ranks were computed on a partial universe:")
        for run_date, n, expected in recent[:5]:
            print(f"[status]   {run_date}: {n} tickers vs a trailing median of {expected} "
                  f"({100.0 * n / expected:.0f}%)")
        print(f"[status] Usually a run that fired before the data vendor published end-of-day bars "
              f"for the whole universe. Re-running on the SAME session date refills it; once the "
              f"market moves on, that day stays partial.")


def _n_sessions_back(db_path, n):
    """The run_date `n` sessions before the latest, or the empty string if history is shorter."""
    cal = storage.live_snapshot_counts(PARAMS["model_version"], db_path=db_path)
    return cal[-n][0] if len(cal) > n else ""


def _run_journal_and_brief(run_result, backfilled, fetch_summary, start_time, db_path, sector_map=None,
                           evaluated_rows=None):
    """Final step of every run: append the structured journal entry, then (best-effort) the AI
    brief. Wrapped so a journal/brief failure can never break a run whose real work — scoring,
    evaluation, CSV export, display — is already done and persisted."""
    if not run_result:
        print("[app] nothing scored this run — skipping journal.")
        return
    warnings = []
    if fetch_summary.get("failed"):
        warnings.append(f"{len(fetch_summary['failed'])} ticker(s) failed price fetch")
    if run_result.get("skipped"):
        warnings.append(f"{len(run_result['skipped'])} ticker(s) skipped (stale / no data)")

    run_context = {
        "run_date": run_result["run_date"],
        "model_version": PARAMS["model_version"],
        "backfilled": backfilled,
        "runtime_sec": time.time() - start_time,
        "tickers_scored": run_result["tickers_scored"],
        "fetch_summary": fetch_summary,
        "fundamentals_summary": None,  # data.fetch_fundamentals logs its own per-run summary
        "warnings": warnings,
        "sector_map": sector_map or {},
    }
    try:
        entry = journal.run_journal(run_context, db_path=db_path, output_dir=OUTPUT_DIR,
                                    evaluated_rows=evaluated_rows)
        brief.run_brief(entry, run_context, db_path=db_path, output_dir=OUTPUT_DIR)
    except Exception as e:  # journal/brief are legibility, not the product — never fatal
        print(f"[app] journal/brief step failed (non-fatal, run already complete): {e}")


if __name__ == "__main__":
    main()
