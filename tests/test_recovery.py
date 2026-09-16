"""Missed-day recovery (self-healing) tests:
- gap detection incl. holes BELOW the max live date, and multi-day gaps;
- run_date derived from DATA not the clock (7am-before-open -> prior session; weekend -> no phantom);
- point-in-time inclusion;
- end-to-end recovery writes LIVE + recovered rows flagged with fundamentals_as_of (multi-day);
- recovered rows excluded from the fundamental-factor IC (lookahead guard), kept elsewhere.
"""

import os
import tempfile

import pandas as pd

import app
from src.config import PARAMS
from src import evaluation, storage


def _temp_db():
    return os.path.join(tempfile.mkdtemp(), "recovery_test.db")


# ---------------------------------------------------------------------------
# Gap detection (pure)
# ---------------------------------------------------------------------------

def test_missing_live_days_detects_hole_below_max_live_date():
    # 07-14 was missed but 07-15 ran, so the hole sits BELOW the max live date — must still be found.
    cal = ["2026-07-13", "2026-07-14", "2026-07-15"]
    live = ["2026-07-13", "2026-07-15"]
    assert app._missing_live_days(cal, live) == ["2026-07-14"]


def test_missing_live_days_multi_day_gap():
    cal = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]
    live = ["2026-07-06", "2026-07-10"]
    assert app._missing_live_days(cal, live) == ["2026-07-07", "2026-07-08", "2026-07-09"]


def test_missing_live_days_none_before_tracking_starts():
    # No live dates yet -> nothing to bridge (first run uses --backfill, never mass-reconstruct).
    assert app._missing_live_days(["2026-07-06", "2026-07-07"], []) == []


def test_missing_live_days_ignores_pre_tracking_history():
    # Sessions before the first live date are left to --backfill, not recovered.
    cal = ["2026-07-01", "2026-07-02", "2026-07-06", "2026-07-07"]
    live = ["2026-07-06", "2026-07-07"]
    assert app._missing_live_days(cal, live) == []


# ---------------------------------------------------------------------------
# run_date derived from DATA, not the clock
# ---------------------------------------------------------------------------

def _spy_bar(d):
    return {"ticker": "SPY", "date": d, "open": 1, "high": 1, "low": 1, "close": 1,
            "volume": 1, "timestamp_fetched": "t"}


def test_latest_trading_date_before_open_uses_prior_session():
    # A catch-up run at 7am (Yahoo has no bar for 'today' yet) records as the prior completed session,
    # regardless of the wall-clock date.
    db = _temp_db()
    storage.init_db(db)
    storage.upsert_price_rows([_spy_bar("2026-07-14"), _spy_bar("2026-07-15")], db_path=db)
    assert storage.latest_trading_date(db_path=db) == "2026-07-15"


def test_latest_trading_date_weekend_no_phantom():
    # A weekend run sees Friday's bar as the max — it never invents a Sat/Sun date.
    db = _temp_db()
    storage.init_db(db)
    storage.upsert_price_rows([_spy_bar("2026-07-10")], db_path=db)   # Friday
    assert storage.latest_trading_date(db_path=db) == "2026-07-10"


# ---------------------------------------------------------------------------
# Point-in-time inclusion
# ---------------------------------------------------------------------------

def test_included_for_date_requires_real_bar_for_ticker_and_benchmark():
    wl = pd.DataFrame([{"ticker": "T1", "benchmark": "SPY", "sector": "X"},
                       {"ticker": "T2", "benchmark": "SPY", "sector": "X"}])
    date_sets = {"T1": {"2026-07-14"}, "T2": set(), "SPY": {"2026-07-14"}}
    assert app._included_for_date(wl, date_sets, "2026-07-14") == [("T1", "SPY", "X")]  # T2 has no bar


# ---------------------------------------------------------------------------
# End-to-end recovery (multi-day) writes flagged live+recovered rows
# ---------------------------------------------------------------------------

def _seed_prices(db, tickers, dates, base=100.0):
    for t in tickers:
        rows = [{"ticker": t, "date": d, "open": base + i, "high": base + i + 1,
                 "low": base + i - 1, "close": base + i, "volume": 1_000_000,
                 "timestamp_fetched": "t"} for i, d in enumerate(dates)]
        storage.upsert_price_rows(rows, db_path=db)


def test_recovery_writes_live_recovered_rows_flagged():
    db = _temp_db()
    storage.init_db(db)
    dates = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]
    _seed_prices(db, ["SPY", "T1", "T2"], dates)
    wl = pd.DataFrame([{"ticker": "T1", "benchmark": "SPY", "sector": "Financials"},
                       {"ticker": "T2", "benchmark": "SPY", "sector": "Financials"}])
    histories = {t: storage.load_price_history(t, db_path=db) for t in ("SPY", "T1", "T2")}
    date_sets = {t: {r["date"] for r in h} for t, h in histories.items()}

    # Seed LIVE snapshots for the first and last sessions only -> 07-07/08/09 form a multi-day gap.
    for d in (dates[0], dates[-1]):
        app.run_scoring_for_date(d, app._included_for_date(wl, date_sets, d), histories, db,
                                 backfilled=False, get_earnings=lambda _t: (None, True),
                                 get_fundamentals=lambda _t: {})

    recovered = app._recover_missing_days(wl, histories, db)
    assert [r["run_date"] for r in recovered] == ["2026-07-07", "2026-07-08", "2026-07-09"]

    # Each recovered day is a LIVE row (backfilled=0) flagged recovered=1.
    #
    # v0.6 CHANGED WHAT fundamentals_as_of MEANS HERE, and the change is the point of this assertion.
    # It used to be the date of the single live fetch (today), stamped onto every recovered day as an
    # honest staleness flag - the recovered row carried TODAY's fundamentals on a PAST date. Now each
    # day resolves its own from EDGAR gated to itself, so fundamentals_as_of IS the recovered date and
    # fundamentals_pit is 1. The mutation this kills: passing `run_date` of the current run, or any
    # single shared date, into the recovery loop - which would put a future filing on a past day and
    # break the no-lookahead invariant, not merely stale-flag it.
    for d in ("2026-07-07", "2026-07-08", "2026-07-09"):
        snaps = storage.load_snapshots_for_date(PARAMS["model_version"], d, db_path=db)
        assert snaps, f"no snapshot written for recovered day {d}"
        assert all(s["backfilled"] == 0 for s in snaps)         # LIVE, not backfill
        assert all(s["recovered"] == 1 for s in snaps)          # flagged recovered
        assert all(s["fundamentals_as_of"] == d for s in snaps), (
            "a recovered day must resolve fundamentals as of ITSELF, never as of the run that "
            "happened to notice it was missing")
        assert all(s["fundamentals_pit"] == 1 for s in snaps)

    # A recovered day now counts as live, so it's no longer a gap next pass (idempotent / converged).
    assert app._missing_live_days(
        storage.get_cached_dates("SPY", db_path=db),
        storage.get_live_run_dates(PARAMS["model_version"], db_path=db),
    ) == []


# ---------------------------------------------------------------------------
# Recovered rows excluded from the fundamental-factor IC only (lookahead guard)
# ---------------------------------------------------------------------------

def test_recovered_excluded_from_fundamental_ic_only():
    # Live rows: value_component perfectly predicts (monotone with excess). Recovered rows: value is
    # ANTI-correlated (its stale fundamentals would drag the IC the wrong way if wrongly included).
    rows = []
    for i in range(30):
        rows.append({"model_version": PARAMS["model_version"], "run_date": "2026-07-10", "backfilled": 0,
                     "recovered": 0, "ticker": f"L{i}", "benchmark": "SPY",
                     "value_component": i, "trend_component": i, "max_drawdown_after_20d": 5.0,
                     "score_20d": 50, "future_excess_return_20d": (i - 15) / 100.0})
    for i in range(30):
        rows.append({"model_version": PARAMS["model_version"], "run_date": "2026-07-14", "backfilled": 0,
                     "recovered": 1, "ticker": f"R{i}", "benchmark": "SPY",
                     "value_component": i, "trend_component": i, "max_drawdown_after_20d": 5.0,
                     "score_20d": 50, "future_excess_return_20d": (15 - i) / 100.0})
    review = evaluation.build_performance_review(rows, model_version=PARAMS["model_version"])
    comp = review[review["report_type"] == "component_correlation"]

    def _ic(component):
        r = comp[(comp["component"] == component) & (comp["horizon"] == "20d")]
        return float(r["spearman_ic"].iloc[0]), int(r["n"].iloc[0])

    v_ic, v_n = _ic("value_component")    # fundamental factor -> recovered rows dropped
    _, t_n = _ic("trend_component")       # price factor -> keeps every row
    assert v_n == 30 and v_ic > 0.99      # only the clean live 30, so IC stays +1
    assert t_n == 60                      # price component keeps live + recovered


def test_edgar_pit_rows_are_included_in_fundamental_ic_even_when_recovered():
    """v0.4 generalizes the fundamental-IC exclusion from `recovered` to `fundamentals_pit`.

    A v0.3 recovered row carries yfinance fundamentals stamped from a LATER fetch, so it must stay out
    of the metric that validates the fundamental factors. A v0.4 recovered row resolves its
    fundamentals from filings gated on filed_date <= D — genuinely point-in-time — so excluding it
    would discard valid evidence from the very factors v0.4 exists to validate. Both rules must hold
    at once, which is exactly what keying off `recovered` alone cannot do."""
    rows = []
    # 30 clean live rows: value_component perfectly predicts.
    for i in range(30):
        rows.append({"model_version": "v0.4_edgar_pit_fundamentals", "run_date": "2026-07-10",
                     "backfilled": 0, "recovered": 0, "fundamentals_pit": 1, "ticker": f"L{i}",
                     "benchmark": "SPY", "value_component": i, "trend_component": i,
                     "max_drawdown_after_20d": 5.0, "score_20d": 50,
                     "future_excess_return_20d": (i - 15) / 100.0})
    # 30 RECOVERED but point-in-time rows (EDGAR): also predictive, and they must be KEPT.
    for i in range(30):
        rows.append({"model_version": "v0.4_edgar_pit_fundamentals", "run_date": "2026-07-14",
                     "backfilled": 0, "recovered": 1, "fundamentals_pit": 1, "ticker": f"P{i}",
                     "benchmark": "SPY", "value_component": i, "trend_component": i,
                     "max_drawdown_after_20d": 5.0, "score_20d": 50,
                     "future_excess_return_20d": (i - 15) / 100.0})
    review = evaluation.build_performance_review(rows, model_version="v0.4_edgar_pit_fundamentals")
    comp = review[review["report_type"] == "component_correlation"]
    r = comp[(comp["component"] == "value_component") & (comp["horizon"] == "20d")]
    assert int(r["n"].iloc[0]) == 60      # PIT recovered rows kept -> all 60, not 30


def test_stale_fundamentals_rule_distinguishes_pit_from_recovered():
    # The single shared definition, exercised directly on the four combinations that matter.
    assert evaluation.has_stale_fundamentals({"recovered": 1, "fundamentals_pit": 0}) is True
    assert evaluation.has_stale_fundamentals({"recovered": 1, "fundamentals_pit": 1}) is False
    assert evaluation.has_stale_fundamentals({"recovered": 0, "fundamentals_pit": 0}) is False
    assert evaluation.has_stale_fundamentals({"recovered": 0}) is False        # legacy row, no column
    assert evaluation.has_stale_fundamentals({"recovered": 1}) is True         # legacy recovered row
    # Section 2/3 grading and the 4a IC must agree, so they share this one function.
    kept = evaluation.exclude_recovered([{"recovered": 1, "fundamentals_pit": 1, "ticker": "A"},
                                         {"recovered": 1, "fundamentals_pit": 0, "ticker": "B"}])
    assert [r["ticker"] for r in kept] == ["A"]


def test_batch_snapshot_write_matches_single_row_write(tmp_path):
    """The backfill writes a whole date in one transaction instead of one commit per ticker (~500x
    fewer fsyncs — the difference between ~24 hours and a normal run). A batch writer that stored
    anything differently from the single-row writer would silently corrupt every backfilled row, so
    the two must produce byte-identical rows, including the NOT NULL coercions and absent columns."""
    from src import storage
    db_a = str(tmp_path / "a.db"); storage.init_db(db_a)
    db_b = str(tmp_path / "b.db"); storage.init_db(db_b)
    rows = [
        {"run_date": "2025-01-02", "ticker": "AAA", "benchmark": "SPY", "model_version": "vX",
         "timestamp_fetched": "t", "backfilled": 1, "earnings_risk_unknown": 1,
         "score_20d": 61.5, "value_component": 70.0, "fundamentals_pit": 1},
        # deliberately omits recovered / fundamentals_pit -> must be coerced to 0, not NULL
        {"run_date": "2025-01-02", "ticker": "BBB", "benchmark": "SPY", "model_version": "vX",
         "timestamp_fetched": "t", "backfilled": 1, "earnings_risk_unknown": 1, "score_20d": None},
    ]
    for r in rows:
        storage.upsert_feature_snapshot(r, db_path=db_a)
    written = storage.upsert_feature_snapshots(rows, db_path=db_b)
    assert written == 2

    a = storage.load_all_snapshots(db_a, model_version="vX")
    b = storage.load_all_snapshots(db_b, model_version="vX")
    assert a == b
    assert [r["fundamentals_pit"] for r in b] == [1, 0]      # coercion applied, no NULLs
    assert [r["recovered"] for r in b] == [0, 0]

    # idempotent: re-running the batch overwrites in place rather than duplicating
    storage.upsert_feature_snapshots(rows, db_path=db_b)
    assert len(storage.load_all_snapshots(db_b, model_version="vX")) == 2
    assert storage.upsert_feature_snapshots([], db_path=db_b) == 0
