"""Analyst estimate revisions — the accumulate-forward table. Synthetic only, no network.

This is the one input in the project that CANNOT be recovered later: Yahoo publishes only where
estimates stand today, so the sample begins the first night the collector runs. That makes two
things load-bearing and both are tested adversarially here:

  1. POINT-IN-TIME reads. An observation recorded on Tuesday must be invisible to a feature computed
     for Monday. Since the table is written forward in real time and read backwards in research, a
     leak here would be undetectable by inspection and would flatter every result built on it.
  2. MISSING IS NOT ZERO. "No analyst revised" and "we have not asked yet" must never collapse into
     the same number — that conflation already manufactured a fake signal once in this project, out
     of an insider-filing publication lag.
"""
import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import data, features, storage


def _db():
    path = os.path.join(tempfile.mkdtemp(), "est.db")
    storage.init_db(path)
    return path


def _row(ticker, fetched_date, period="+1y", **kw):
    row = {"ticker": ticker, "fetched_date": fetched_date, "period": period,
           "fetch_failed": 0, "timestamp_fetched": "t"}
    row.update(kw)
    return row


# ---------------------------------------------------------------------------
# The no-lookahead gate
# ---------------------------------------------------------------------------

def test_an_observation_recorded_later_is_invisible_to_an_earlier_date():
    """THE invariant. The mutation this kills: dropping `fetched_date <= ?` from the read, which
    would silently give every historical feature tomorrow's consensus."""
    db = _db()
    storage.upsert_estimate_rows([
        _row("AAA", "2026-01-10", eps_current=5.0, eps_30d_ago=4.0),
        _row("AAA", "2026-02-10", eps_current=9.0, eps_30d_ago=4.0),
    ], db_path=db)

    on_jan = storage.get_estimates_as_of("AAA", "2026-01-15", db_path=db)
    assert on_jan["+1y"]["eps_current"] == 5.0, "a February observation leaked into a January read"
    assert storage.get_estimates_as_of("AAA", "2026-02-15", db_path=db)["+1y"]["eps_current"] == 9.0
    assert storage.get_estimates_as_of("AAA", "2026-01-09", db_path=db) == {}


def test_the_read_returns_the_freshest_row_at_or_before_the_date_not_the_first():
    db = _db()
    for d, v in (("2026-01-02", 1.0), ("2026-01-20", 2.0), ("2026-01-11", 3.0)):
        storage.upsert_estimate_rows([_row("AAA", d, eps_current=v)], db_path=db)
    assert storage.get_estimates_as_of("AAA", "2026-01-15", db_path=db)["+1y"]["eps_current"] == 3.0


def test_a_later_write_never_overwrites_an_earlier_observation():
    """Append-only is what makes the history trustworthy: re-running a day is idempotent, but the
    record of what was believed on an earlier day is immutable."""
    db = _db()
    storage.upsert_estimate_rows([_row("AAA", "2026-01-10", eps_current=5.0)], db_path=db)
    storage.upsert_estimate_rows([_row("AAA", "2026-01-11", eps_current=6.0)], db_path=db)
    storage.upsert_estimate_rows([_row("AAA", "2026-01-10", eps_current=5.0)], db_path=db)  # re-run
    assert storage.get_estimates_as_of("AAA", "2026-01-10", db_path=db)["+1y"]["eps_current"] == 5.0
    n, tickers, first, last = storage.estimate_coverage(db_path=db)
    assert (n, tickers, first, last) == (2, 1, "2026-01-10", "2026-01-11")


# ---------------------------------------------------------------------------
# Missing is not zero
# ---------------------------------------------------------------------------

def test_never_observed_reports_missing_rather_than_zero():
    db = _db()
    f = features.estimate_features_as_of("NOPE", "2026-01-15", db_path=db)
    assert f["estimates_missing"] is True
    for k in ("eps_revision_1m", "eps_revision_3m", "eps_revision_breadth_30d"):
        assert f[k] is None, f"{k} must be None when unobserved, never 0"


def test_a_failed_observation_is_not_read_as_a_real_reading():
    db = _db()
    storage.upsert_estimate_rows([
        {"ticker": "ETF", "fetched_date": "2026-01-10", "period": "+1y",
         "fetch_failed": 1, "timestamp_fetched": "t"}], db_path=db)
    assert features.estimate_features_as_of("ETF", "2026-01-15", db_path=db)["estimates_missing"]


def test_a_genuine_zero_revision_count_is_distinguishable_from_no_data():
    """0 ups and 0 downs is a REAL reading ("nobody moved"), and must not be reported as missing
    data — but breadth is undefined on it, so it stays None rather than being called 0."""
    db = _db()
    storage.upsert_estimate_rows([
        _row("AAA", "2026-01-10", eps_current=5.0, eps_30d_ago=4.0,
             up_last_30d=0.0, down_last_30d=0.0)], db_path=db)
    f = features.estimate_features_as_of("AAA", "2026-01-15", db_path=db)
    assert f["eps_revision_up_30d"] == 0.0 and f["eps_revision_down_30d"] == 0.0
    assert f["eps_revision_breadth_30d"] is None, "breadth on 0 of 0 is undefined, not neutral"
    assert f["estimates_missing"] is False, "the estimate itself WAS observed"


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------

def test_revision_arithmetic_and_breadth():
    db = _db()
    storage.upsert_estimate_rows([
        _row("AAA", "2026-01-10", eps_current=5.5, eps_30d_ago=5.0, eps_90d_ago=4.4,
             up_last_30d=8.0, down_last_30d=2.0)], db_path=db)
    f = features.estimate_features_as_of("AAA", "2026-01-12", db_path=db)
    assert f["eps_revision_1m"] == pytest.approx(0.10)
    assert f["eps_revision_3m"] == pytest.approx(0.25)
    assert f["eps_revision_breadth_30d"] == pytest.approx(0.6)
    assert f["eps_estimate_age_days"] == 2, "a thin rolling sample must expose its own staleness"


def test_a_loss_narrowing_counts_as_an_upward_revision():
    """-0.50 -> -0.25 is unambiguously an improvement. A raw (now-then)/then denominator reports it
    as -50%, inverting the sign of the signal for exactly the distressed names where revisions
    matter most. The mutation this kills: dropping the abs() from the denominator."""
    assert features._pct_change(-0.25, -0.50) == pytest.approx(0.5)
    assert features._pct_change(-0.75, -0.50) == pytest.approx(-0.5)


def test_pct_change_refuses_a_zero_or_missing_base():
    assert features._pct_change(1.0, 0) is None      # undefined, not infinite
    assert features._pct_change(None, 1.0) is None
    assert features._pct_change(1.0, None) is None


# ---------------------------------------------------------------------------
# Flattening yfinance's two frames
# ---------------------------------------------------------------------------

def _frames():
    trend = pd.DataFrame(
        {"current": [2.0, 9.0], "7daysAgo": [1.9, 8.9], "30daysAgo": [1.8, 8.8],
         "60daysAgo": [1.7, 8.7], "90daysAgo": [1.6, 8.6], "currency": ["USD", "USD"]},
        index=["0q", "+1y"])
    revisions = pd.DataFrame(
        {"upLast7days": [1, 3], "upLast30days": [5, 7], "downLast30days": [2, 1],
         "downLast7Days": [0, 1], "currency": ["USD", "USD"]},
        index=["0q", "+1y"])
    return trend, revisions


def test_flatten_reads_both_frames_including_yahoos_capital_d_spelling():
    """Yahoo spells one column 'downLast7Days' and the rest lowercase. Missing it would read as
    "no analyst revised down" — a fabricated zero, not a missing value."""
    trend, revisions = _frames()
    rows = {r["period"]: r for r in
            data._estimate_rows_for_ticker("AAA", trend, revisions, "2026-01-10", "ts")}
    assert set(rows) == {"0q", "+1y"}
    assert rows["+1y"]["eps_current"] == 9.0 and rows["+1y"]["eps_90d_ago"] == 8.6
    assert rows["+1y"]["down_last_7d"] == 1.0, "the capital-D spelling was not read"
    assert rows["0q"]["down_last_7d"] == 0.0
    assert rows["+1y"]["currency"] == "USD"


def test_flatten_unions_periods_so_a_partial_observation_is_still_recorded():
    """A ticker with a trend but no revision counts is real data. Intersecting the frames would
    silently drop it and shrink a sample that cannot be regrown."""
    trend, _ = _frames()
    rows = {r["period"]: r for r in
            data._estimate_rows_for_ticker("AAA", trend, None, "2026-01-10", "ts")}
    assert set(rows) == {"0q", "+1y"}
    assert rows["+1y"]["eps_current"] == 9.0
    assert rows["+1y"]["up_last_30d"] is None, "absent revision counts must be None, not 0"


def test_flatten_survives_empty_and_malformed_frames():
    assert data._estimate_rows_for_ticker("AAA", None, None, "2026-01-10", "ts") == []
    assert data._estimate_rows_for_ticker("AAA", pd.DataFrame(), pd.DataFrame(),
                                          "2026-01-10", "ts") == []
    odd = pd.DataFrame({"current": ["not-a-number"]}, index=["+1y"])
    rows = data._estimate_rows_for_ticker("AAA", odd, None, "2026-01-10", "ts")
    assert rows[0]["eps_current"] is None, "an unparseable cell must be None, never coerced"


# ---------------------------------------------------------------------------
# The rolling queue
# ---------------------------------------------------------------------------

def test_the_rolling_slice_asks_the_least_recently_seen_names_first(monkeypatch):
    """Without oldest-first ordering the same slice would be re-asked nightly and most of the
    universe would never be recorded at all — and unlike price history, the nights missed while
    that went unnoticed could never be recovered."""
    db = _db()
    storage.upsert_estimate_rows([
        _row("SEEN_RECENTLY", "2026-01-09"), _row("SEEN_LONG_AGO", "2025-06-01")], db_path=db)

    asked = []

    class _FakeTicker:
        def __init__(self, t):
            asked.append(t)
            self.eps_trend, self.eps_revisions = _frames()

    monkeypatch.setattr(data.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(data.time, "sleep", lambda *_a: None)
    data.fetch_estimate_revisions(
        ["SEEN_RECENTLY", "SEEN_LONG_AGO", "NEVER_SEEN"], db_path=db,
        refresh_days=3, as_of_date="2026-01-10")

    assert asked == ["NEVER_SEEN"], f"expected the never-seen name first, asked {asked}"


def test_a_ticker_with_no_coverage_is_recorded_as_failed_not_retried_forever(monkeypatch):
    """An ETF has no analyst estimates. Writing nothing would leave it permanently 'never seen', so
    it would win the oldest-first queue every single night and starve every other name."""
    db = _db()

    class _EmptyTicker:
        def __init__(self, t):
            self.eps_trend, self.eps_revisions = None, None

    monkeypatch.setattr(data.yf, "Ticker", _EmptyTicker)
    monkeypatch.setattr(data.time, "sleep", lambda *_a: None)
    data.fetch_estimate_revisions(["SPY"], db_path=db, refresh_days=1, as_of_date="2026-01-10")

    rows = storage.get_estimates_as_of("SPY", "2026-01-10", db_path=db)
    assert rows and rows["none"]["fetch_failed"] == 1
    assert storage.estimate_coverage(db_path=db)[0] == 0, "a failed probe is not coverage"


def test_a_fetch_error_is_skipped_without_writing_anything(monkeypatch):
    db = _db()

    class _Boom:
        def __init__(self, t):
            raise RuntimeError("yahoo said no")

    monkeypatch.setattr(data.yf, "Ticker", _Boom)
    monkeypatch.setattr(data.time, "sleep", lambda *_a: None)
    assert data.fetch_estimate_revisions(["AAA"], db_path=db, refresh_days=1,
                                         as_of_date="2026-01-10") == 0
    assert storage.get_estimates_as_of("AAA", "2026-01-10", db_path=db) == {}


# ---------------------------------------------------------------------------
# It must NOT be scored yet
# ---------------------------------------------------------------------------

def test_estimate_features_are_collected_but_not_wired_into_any_score():
    """Feeding a live-only input into the score is the exact failure v0.6 exists to undo: it would
    create a factor no backfilled row could carry and re-split one model_version into two models.
    These features earn a place by being MEASURED first, which needs history this table lacks.

    The mutation this kills: quietly adding an estimate column to the scored set before the
    measurement exists."""
    from src.config import SCORE_WEIGHTS_BY_VERSION
    est_fields = ("eps_revision_1m", "eps_revision_3m", "eps_revision_breadth_30d")
    for col in storage.RAW_FEATURE_COLUMNS + storage.SCORE_COLUMNS:
        assert not any(col.startswith(e) for e in est_fields), (
            f"{col} entered the snapshot's scored columns before any validation existed")
    for weights in SCORE_WEIGHTS_BY_VERSION.values():
        for comp in weights:
            assert "revision" not in comp and "estimate" not in comp
