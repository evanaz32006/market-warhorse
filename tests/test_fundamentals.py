"""v0.2 proof tests: the fundamentals/short-interest layer and the sit-out renormalization.

Covers every "Validation additions" bullet from the v0.2 spec:
- a ticker missing ALL fundamentals still gets a valid renormalized price/volume score;
- a negative P/E is treated as missing, not as "cheap";
- horizon weights renormalize to sum to 1 when components sit out;
- the >40%-missing sparse warning warns instead of crashing.
Plus: composite percentiles rank over present-only, short_ratio stays out of the composite,
negative-scrub of every valuation ratio, and the throttled cache reuse path (no network).
"""

import os
import tempfile

import pytest

import app
from src import data, features, scoring, storage
from src.config import COMPONENT_PARAMS, FUNDAMENTAL_FIELDS, SCORE_WEIGHTS, SITOUT_COMPONENTS


# ---------------------------------------------------------------------------
# features.compute_fundamental_features — negative scrub + missing flags
# ---------------------------------------------------------------------------

def test_negative_pe_is_treated_as_missing_not_cheap():
    out = features.compute_fundamental_features({
        "trailing_pe": -12.0,      # no earnings -> NOT cheap -> missing
        "price_to_sales": 3.0,     # legitimately present
        "ev_to_ebitda": -4.0,      # negative -> missing
        "price_to_book": 2.0,
    })
    assert out["trailing_pe"] is None
    assert out["ev_to_ebitda"] is None
    assert out["price_to_sales"] == 3.0 and out["price_to_book"] == 2.0
    # two of four value ratios still present -> the value family is NOT missing
    assert out["value_missing"] is False


def test_zero_valuation_ratio_is_treated_as_missing():
    out = features.compute_fundamental_features({"price_to_book": 0.0, "trailing_pe": 15.0})
    assert out["price_to_book"] is None
    assert out["trailing_pe"] == 15.0


def test_ticker_with_no_fundamentals_flags_every_family_missing():
    out = features.compute_fundamental_features({})
    assert out["fundamentals_missing"] is True
    assert out["value_missing"] and out["quality_missing"] and out["short_interest_missing"]
    assert all(out[f] is None for f in FUNDAMENTAL_FIELDS)


# ---------------------------------------------------------------------------
# scoring.compute_percentiles — composites over present-only
# ---------------------------------------------------------------------------

def _three_ticker_pool():
    # A cheapest / highest quality / least shorted; B the opposite; C has no fundamentals.
    return {
        "A": {"trailing_pe": 10, "price_to_sales": 2, "ev_to_ebitda": 8, "price_to_book": 1,
              "profit_margin": 0.30, "operating_margin": 0.30, "return_on_equity": 0.40,
              "debt_to_equity": 40, "current_ratio": 2.5,
              "short_percent_of_float": 0.02, "short_ratio": 1.0},
        "B": {"trailing_pe": 45, "price_to_sales": 12, "ev_to_ebitda": 33, "price_to_book": 7,
              "profit_margin": 0.04, "operating_margin": 0.05, "return_on_equity": 0.05,
              "debt_to_equity": 220, "current_ratio": 0.8,
              "short_percent_of_float": 0.25, "short_ratio": 9.0},
        "C": {f: None for f in FUNDAMENTAL_FIELDS},
    }


def test_composite_percentiles_rank_over_present_only_and_none_when_absent():
    pct = scoring.compute_percentiles(_three_ticker_pool())
    # cheaper/higher-quality/less-shorted A ranks above B on all three composites
    assert pct["A"]["value_percentile"] > pct["B"]["value_percentile"]
    assert pct["A"]["quality_percentile"] > pct["B"]["quality_percentile"]
    assert pct["A"]["short_interest_percentile"] > pct["B"]["short_interest_percentile"]
    # C has nothing -> all three composites are None (family sits out), never defaulted
    assert pct["C"]["value_percentile"] is None
    assert pct["C"]["quality_percentile"] is None
    assert pct["C"]["short_interest_percentile"] is None


def test_short_ratio_is_not_part_of_the_short_interest_composite():
    # Two tickers with IDENTICAL short_percent_of_float but very different short_ratio must get
    # the SAME short_interest_percentile — proving short_ratio is context only, not scored.
    pool = {
        "X": {"short_percent_of_float": 0.05, "short_ratio": 1.0},
        "Y": {"short_percent_of_float": 0.05, "short_ratio": 20.0},
    }
    pct = scoring.compute_percentiles(pool)
    assert pct["X"]["short_interest_percentile"] == pytest.approx(pct["Y"]["short_interest_percentile"])


def test_quality_composite_excludes_current_ratio():
    # Identical quality inputs but wildly different current_ratio -> identical quality_percentile.
    base = {"profit_margin": 0.2, "operating_margin": 0.2, "return_on_equity": 0.2, "debt_to_equity": 100}
    pool = {
        "P": dict(base, current_ratio=0.5),
        "Q": dict(base, current_ratio=5.0),
    }
    pct = scoring.compute_percentiles(pool)
    assert pct["P"]["quality_percentile"] == pytest.approx(pct["Q"]["quality_percentile"])


# ---------------------------------------------------------------------------
# scoring — components sit out; horizon renormalizes
# ---------------------------------------------------------------------------

def test_fundamental_components_none_when_percentile_missing():
    comps = scoring.compute_all_components(
        {f: None for f in FUNDAMENTAL_FIELDS},
        {"value_percentile": None, "quality_percentile": None, "short_interest_percentile": None},
        ticker="C",
    )
    assert comps["value_component"] is None
    assert comps["quality_component"] is None
    assert comps["short_interest_component"] is None


def _all_mandatory_present(value=70.0):
    """Every non-sit-out component across all horizons, set to a constant value."""
    comps = {}
    for weight_map in SCORE_WEIGHTS.values():
        for comp in weight_map:
            if comp not in SITOUT_COMPONENTS:
                comps[comp] = value
    return comps


def test_ticker_missing_all_fundamentals_still_scores_on_price_volume():
    comps = _all_mandatory_present(70.0)
    comps.update({c: None for c in SITOUT_COMPONENTS})  # every fundamental family sits out
    scores = scoring.compute_horizon_scores(comps, earnings_risk_unknown=True)
    # all four horizons must be valid (not None) and — since every present component is 70 and
    # the surviving weights renormalize to 1 — must equal exactly 70.
    for horizon, score in scores.items():
        assert score is not None, f"{horizon} went None despite valid price/volume components"
        assert score == pytest.approx(70.0), f"{horizon}={score}, weights did not renormalize to 1"


def test_weights_renormalize_to_one_when_components_sit_out():
    # Mandatory components at 100, fundamentals absent: the score must be the mandatory-only
    # weighted average renormalized to 1, i.e. exactly 100 (not diluted toward 0 by the missing
    # weight). Confirms the divide-by-present-weight renormalization.
    comps = _all_mandatory_present(100.0)
    comps.update({c: None for c in SITOUT_COMPONENTS})
    scores = scoring.compute_horizon_scores(comps, earnings_risk_unknown=True)
    for horizon, score in scores.items():
        assert score == pytest.approx(100.0), f"{horizon}={score} — renormalization failed"


def test_missing_mandatory_component_still_nulls_the_horizon():
    # trend_component is mandatory (price/volume); its absence must null every horizon that
    # weights it, exactly as in v0.1 — sit-out applies ONLY to fundamentals.
    comps = _all_mandatory_present(80.0)
    comps.update({c: 80.0 for c in SITOUT_COMPONENTS})
    comps["trend_component"] = None
    scores = scoring.compute_horizon_scores(comps, earnings_risk_unknown=True)
    assert all(score is None for score in scores.values())


def test_partial_fundamentals_blend_between_mandatory_and_present_fundamentals():
    # Mandatory at 60, value present at 100 (quality/short still out): score must land strictly
    # between 60 and 100 — the present fundamental pulls it up, renormalized.
    comps = _all_mandatory_present(60.0)
    comps.update({"value_component": 100.0, "quality_component": None, "short_interest_component": None})
    scores = scoring.compute_horizon_scores(comps, earnings_risk_unknown=True)
    for horizon, score in scores.items():
        assert 60.0 < score < 100.0, f"{horizon}={score}"


# ---------------------------------------------------------------------------
# app — sparse-fundamental warning warns, never crashes
# ---------------------------------------------------------------------------

def test_sparse_fundamentals_warning_warns_but_does_not_crash(capsys):
    # 3 of 4 tickers missing trailing_pe (75% > 40% threshold) -> a warning line, no exception.
    features_by_ticker = {
        "A": {f: None for f in FUNDAMENTAL_FIELDS},
        "B": {f: None for f in FUNDAMENTAL_FIELDS},
        "C": {f: None for f in FUNDAMENTAL_FIELDS},
        "D": dict({f: None for f in FUNDAMENTAL_FIELDS}, trailing_pe=20.0),
    }
    app._warn_sparse_fundamentals(features_by_ticker)  # must not raise
    out = capsys.readouterr().out
    assert "trailing_pe" in out and "missing" in out


# ---------------------------------------------------------------------------
# data.fetch_fundamentals — cache reuse (no network) and fetch/store path
# ---------------------------------------------------------------------------

def _temp_db():
    d = tempfile.mkdtemp()
    return os.path.join(d, "test.db")


def test_fetch_fundamentals_reuses_fresh_cache_without_network(monkeypatch):
    db = _temp_db()
    storage.init_db(db)
    from datetime import datetime, timezone
    storage.upsert_fundamentals("AAA", {"trailing_pe": 30.0, "short_percent_of_float": 0.03},
                                datetime.now(timezone.utc).isoformat(), db_path=db)

    def _boom(*a, **k):
        raise AssertionError("network fetch attempted despite a fresh cache")

    monkeypatch.setattr(data.yf, "Ticker", _boom)
    monkeypatch.setattr(data.time, "sleep", lambda *_a, **_k: None)
    result = data.fetch_fundamentals(["AAA"], db_path=db)
    assert result["AAA"]["trailing_pe"] == 30.0
    assert result["AAA"]["short_percent_of_float"] == 0.03


def test_fetch_fundamentals_fetches_and_stores_when_uncached(monkeypatch):
    db = _temp_db()
    storage.init_db(db)

    class _FakeTicker:
        def __init__(self, _t):
            self.info = {"trailingPE": 18.0, "profitMargins": 0.15, "shortPercentOfFloat": 0.06}

    monkeypatch.setattr(data.yf, "Ticker", _FakeTicker)
    monkeypatch.setattr(data.time, "sleep", lambda *_a, **_k: None)
    result = data.fetch_fundamentals(["BBB"], db_path=db)
    assert result["BBB"]["trailing_pe"] == 18.0
    assert result["BBB"]["profit_margin"] == 0.15
    # persisted to the cache table for next time
    cached = storage.get_cached_fundamentals("BBB", db_path=db)
    assert cached["trailing_pe"] == 18.0 and cached["fetch_failed"] == 0


def test_fetch_fundamentals_is_failsoft_when_info_raises(monkeypatch):
    db = _temp_db()
    storage.init_db(db)

    def _raise(_t):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(data.yf, "Ticker", _raise)
    monkeypatch.setattr(data.time, "sleep", lambda *_a, **_k: None)
    result = data.fetch_fundamentals(["CCC"], db_path=db)  # must not raise
    assert result["CCC"] == {f: None for f in FUNDAMENTAL_FIELDS}
