"""v0.6 — the live row and the backfilled row must be the SAME MODEL.

THE BUG THIS FILE EXISTS TO PREVENT (measured on the v0.5 rows, 2026-09-16):

                              live (27,396 rows)         backfilled (777,738 rows)
    fundamentals_pit          0 on every row             1 on every row
    fundamentals source       yfinance CURRENT snapshot  EDGAR, gated filed_date <= D
    short_interest_component  present on 26,744          NULL on all 777,738
    earnings penalty          applied to 289 rows        applied to 0

One `model_version` string covered two different models. Every historical number the project had
produced described the backfilled one, while the nightly run produced the other — so the only
genuinely out-of-sample rows were scored by a model nothing had ever validated.

The one-off proof was run on real data: the live path and the backfill path over 1,526 tickers on
2026-08-19, 33 fields each, ZERO differences. These tests are the standing version of that proof,
on synthetic data so they run in milliseconds and cannot silently regress.
"""
import os
import sys
import tempfile

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from src import storage
from src.config import (EARNINGS_PENALTIES, LIVE_EARNINGS_PENALTY_VERSIONS, NO_EARNINGS_PENALTIES,
                        PARAMS, SCORE_WEIGHTS_BY_VERSION)


def _db():
    return os.path.join(tempfile.mkdtemp(), "parity.db")


def _seed(db, tickers, n_days=260, base=100.0):
    """A long-enough synthetic history that every trailing window resolves — otherwise the scores
    are all None and a parity test passes vacuously."""
    dates = [f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n_days)]
    for k, t in enumerate(tickers):
        rows = [{"ticker": t, "date": d, "open": base + k + i * 0.1,
                 "high": base + k + i * 0.1 + 1, "low": base + k + i * 0.1 - 1,
                 "close": base + k + i * 0.1, "volume": 1_000_000 + 1000 * i,
                 "timestamp_fetched": "t"} for i, d in enumerate(dates)]
        storage.upsert_price_rows(rows, db_path=db)
    return dates


def _score(db, version, backfilled, as_of, wl, histories, get_earnings, get_fundamentals):
    date_sets = {t: {r["date"] for r in h} for t, h in histories.items()}
    included = app._included_for_date(wl, date_sets, as_of)
    assert included, "fixture produced no scorable names — the test would pass vacuously"
    app.run_scoring_for_date(as_of, included, histories, db, backfilled=backfilled,
                             get_earnings=get_earnings, get_fundamentals=get_fundamentals,
                             model_version=version, fundamentals_pit=True)
    return {r["ticker"]: r for r in storage.load_snapshots_for_date(version, as_of, db_path=db)}


def _fixture():
    db = _db()
    storage.init_db(db)
    tickers = ["SPY", "AAA", "BBB", "CCC", "DDD"]
    dates = _seed(db, tickers)
    wl = pd.DataFrame([{"ticker": t, "benchmark": "SPY", "sector": "Financials"}
                       for t in tickers if t != "SPY"])
    histories = {t: storage.load_price_history(t, db_path=db) for t in tickers}
    return db, wl, histories, dates[-1]


# ---------------------------------------------------------------------------
# The parity itself
# ---------------------------------------------------------------------------

def test_live_and_backfill_paths_produce_identical_rows():
    """Same date, same history, same fundamentals provider, differing ONLY in `backfilled`.

    The mutation this kills: reintroducing any live-only input to scoring — a second fundamentals
    source, a live-only component, a penalty that fires on one path — which is precisely how v0.5
    ended up holding two models under one version string."""
    db, wl, histories, as_of = _fixture()
    fund = lambda _t, _f=None: {"trailing_pe": 15.0, "profit_margin": 0.2, "return_on_equity": 0.3}
    no_earnings = lambda _t: (None, True)

    live = _score(db, "parity_live", False, as_of, wl, histories, no_earnings, fund)
    back = _score(db, "parity_back", True, as_of, wl, histories, no_earnings, fund)

    assert set(live) == set(back)
    fields = [c for c in storage.SCORE_COLUMNS] + [
        "trailing_pe", "profit_margin", "return_on_equity",
        "value_percentile", "quality_percentile", "latest_close", "fundamentals_pit"]
    scored = 0
    for t in live:
        for c in fields:
            assert live[t].get(c) == back[t].get(c), f"{t}.{c} diverged between live and backfill"
        scored += live[t].get("score_120d") is not None
    assert scored, "no row produced a score — parity held only because everything was None"


def test_the_earnings_penalty_is_decided_by_version_not_by_caller():
    """The penalty was the one live-only element left, and it fired on 289 v0.5 rows that no
    backfilled row could ever match. It is now resolved from `model_version` inside the single
    function both paths call, so there is no per-caller flag anyone can forget to pass.

    The mutation this kills: re-adding an `apply_penalty=True` argument at a call site."""
    assert PARAMS["model_version"] not in LIVE_EARNINGS_PENALTY_VERSIONS, (
        "the ACTIVE version must not apply a live-only penalty the backfill cannot reproduce")
    assert any(v in LIVE_EARNINGS_PENALTY_VERSIONS for v in SCORE_WEIGHTS_BY_VERSION), (
        "the set must still record which past versions DID apply it, or history is misdescribed")
    assert set(NO_EARNINGS_PENALTIES) == set(EARNINGS_PENALTIES)
    assert set(NO_EARNINGS_PENALTIES.values()) == {0}


def test_a_near_earnings_name_scores_the_same_on_both_paths():
    """The live path is the only one that ever has an earnings date. Under the active version a name
    reporting tomorrow must still score exactly as the backfill would score it."""
    db, wl, histories, as_of = _fixture()
    fund = lambda _t, _f=None: {"trailing_pe": 15.0}
    import datetime
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    # The LIVE side must run under the ACTIVE model_version, because that is what decides whether the
    # penalty fires. Scoring it under an invented version name would make this test unable to detect
    # the very regression it exists for (confirmed by mutation: it passed with the penalty re-enabled).
    live = _score(db, PARAMS["model_version"], False, as_of, wl, histories,
                  lambda _t: (tomorrow, False), fund)          # earnings KNOWN and imminent
    back = _score(db, "parity_back2", True, as_of, wl, histories,
                  lambda _t: (None, True), fund)               # backfill never knows

    for t in live:
        assert live[t]["days_until_earnings"] == 1, "the earnings date must still be COLLECTED"
        assert live[t]["earnings_risk_unknown"] == 0
        for h in ("score_5d", "score_20d", "score_60d", "score_120d"):
            assert live[t].get(h) == back[t].get(h), (
                f"{t}.{h}: a live row near earnings was scored on a different formula than the "
                f"backfill — the exact divergence v0.6 exists to remove")


def test_the_resolver_cannot_be_asked_for_a_date_other_than_its_own():
    """`edgar_fundamentals_resolver` closes over as_of_date. A caller holding one built for D
    cannot use it to resolve D+1, which is what keeps recovery from stamping today's filings onto
    a past day."""
    seen = {}

    class _FakeEdgar:
        @staticmethod
        def get_fundamentals_as_of(ticker, as_of, price=None, sector=None, db_path=None,
                                   facts_index=None):
            seen[ticker] = as_of
            return {"trailing_pe": 1.0}

    import src.edgar as real_edgar
    get_fund = app.edgar_fundamentals_resolver("2026-01-05", {"AAA": "Financials"}, "ignored.db")
    # the closure takes its date from construction, never from the call
    import unittest.mock as mock
    with mock.patch.object(real_edgar, "get_fundamentals_as_of",
                           _FakeEdgar.get_fundamentals_as_of):
        get_fund("AAA", {"latest_close": 10.0})
    assert seen == {"AAA": "2026-01-05"}


# ---------------------------------------------------------------------------
# Frozen-version refresh rotation
# ---------------------------------------------------------------------------

def test_rolling_refresh_picks_the_stalest_version_first(tmp_path):
    """Without oldest-first ordering the same version would be recomputed every night and the
    others would never refresh at all — a rotation that does not rotate."""
    from src import evaluation
    path = str(tmp_path / "performance_review.csv")
    pd.DataFrame([
        {"model_version": "a", "recomputed_on": "2026-09-10"},
        {"model_version": "b", "recomputed_on": "2026-09-01"},
        {"model_version": "c", "recomputed_on": "2026-09-05"},
    ]).to_csv(path, index=False)
    assert evaluation._rolling_frozen_refresh(["a", "b", "c"], path, 1) == ["b"]
    assert evaluation._rolling_frozen_refresh(["a", "b", "c"], path, 2) == ["b", "c"]


def test_a_version_never_recomputed_sorts_ahead_of_every_dated_one(tmp_path):
    from src import evaluation
    path = str(tmp_path / "performance_review.csv")
    pd.DataFrame([{"model_version": "a", "recomputed_on": "2026-09-01"}]).to_csv(path, index=False)
    assert evaluation._rolling_frozen_refresh(["a", "zzz_never_seen"], path, 1) == ["zzz_never_seen"]


def test_rolling_refresh_survives_a_missing_or_unstamped_report(tmp_path):
    """A report written before `recomputed_on` existed must not crash the chooser or make it
    silently refresh nothing."""
    from src import evaluation
    missing = str(tmp_path / "nope.csv")
    assert evaluation._rolling_frozen_refresh(["a", "b"], missing, 1) == ["a"]
    old = str(tmp_path / "old.csv")
    pd.DataFrame([{"model_version": "a", "n": 1}]).to_csv(old, index=False)
    assert evaluation._rolling_frozen_refresh(["a", "b"], old, 1) == ["a"]
    assert evaluation._rolling_frozen_refresh(["a", "b"], old, 0) == []
