"""Stage 2 proof tests: hand-computed percentile pools, component formulas, the one
documented missing-input fallback (long_momentum_component), and the missing-input ->
None propagation policy for components with no defined fallback.
"""

import pytest

from src import scoring
from src.config import COMPONENT_PARAMS


def test_percentile_rank_ascending_known_pool():
    features_by_ticker = {
        "A": {"return_5d": 0.01},
        "B": {"return_5d": 0.05},
        "C": {"return_5d": 0.10},
    }
    out = scoring.compute_percentiles(features_by_ticker)
    assert out["A"]["return_5d_percentile"] == pytest.approx(33.333, rel=1e-3)
    assert out["B"]["return_5d_percentile"] == pytest.approx(66.667, rel=1e-3)
    assert out["C"]["return_5d_percentile"] == pytest.approx(100.0)


def test_percentile_rank_inverted_known_pool():
    features_by_ticker = {
        "A": {"ATR_pct": 0.01},
        "B": {"ATR_pct": 0.03},
        "C": {"ATR_pct": 0.05},
    }
    out = scoring.compute_percentiles(features_by_ticker)
    # lowest raw risk (A) should rank HIGHEST.
    assert out["A"]["ATR_pct_percentile"] == pytest.approx(100.0)
    assert out["B"]["ATR_pct_percentile"] == pytest.approx(66.667, rel=1e-3)
    assert out["C"]["ATR_pct_percentile"] == pytest.approx(33.333, rel=1e-3)


def test_distance_from_52w_high_adjusted_percentile_caps_extended_tickers():
    features_by_ticker = {
        "A": {"distance_from_52w_high_pct": 1.0, "extended_flag": True},
        "B": {"distance_from_52w_high_pct": 3.0, "extended_flag": False},
        "C": {"distance_from_52w_high_pct": 5.0, "extended_flag": False},
    }
    out = scoring.compute_percentiles(features_by_ticker)
    # Without the cap, A (closest to high) would rank 100 — but extended_flag caps it at 50.
    assert out["A"]["distance_from_52w_high_adjusted_percentile"] == pytest.approx(50.0)
    assert out["B"]["distance_from_52w_high_adjusted_percentile"] == pytest.approx(66.667, rel=1e-3)
    assert out["C"]["distance_from_52w_high_adjusted_percentile"] == pytest.approx(33.333, rel=1e-3)


def test_trend_component_exactly_three_of_five_conditions():
    # close>SMA20 (T), close>SMA50 (F), close>SMA200 (T), SMA20>SMA50 (F), SMA50>SMA200 (T)
    features = {"latest_close": 110, "SMA20": 100, "SMA50": 120, "SMA200": 90}
    score = scoring.trend_component(features, COMPONENT_PARAMS["trend_component"])
    assert score == pytest.approx(60.0)


def test_long_momentum_component_falls_back_when_return_252d_missing():
    features = {"return_120d": 0.05}
    percentiles = {
        "return_120d_percentile": 70.0,
        "return_60d_percentile": 80.0,
        "return_252d_percentile": None,  # missing -> fallback to return_120d_percentile
    }
    params = COMPONENT_PARAMS["long_momentum_component"]
    score = scoring.long_momentum_component(features, percentiles, params)
    expected = params["w_return_120d_pct"] * 70.0 + params["w_return_252d_pct"] * 70.0 + params["w_return_60d_pct"] * 80.0
    assert score == pytest.approx(expected)


def test_short_momentum_component_returns_none_with_no_fallback_for_missing_input():
    features = {"return_5d": 0.01, "return_10d": 0.01}
    percentiles = {
        "return_5d_percentile": None,  # missing, no fallback defined for this component
        "return_10d_percentile": 60.0,
        "return_20d_percentile": 60.0,
    }
    score = scoring.short_momentum_component(features, percentiles, COMPONENT_PARAMS["short_momentum_component"])
    assert score is None


def test_horizon_score_is_none_when_a_weighted_component_is_none():
    components = {
        "trend_component": 80.0,
        "momentum_component_20d": None,  # missing -> score_20d must propagate None
        "relative_strength_component_20d": 70.0,
        "volume_behavior_component": 60.0,
        "risk_component": 50.0,
        "setup_component": 50.0,
        "market_regime_component": 50.0,
    }
    scores = scoring.compute_horizon_scores(components, days_until_earnings=None, earnings_risk_unknown=True)
    assert scores["score_20d"] is None


def test_label_for_score_has_no_gaps_between_integer_bands():
    # 79.2 falls between the spec's literal "65-79 decent" and "80-100 strong" bands —
    # must still resolve to a label, not None.
    assert scoring.label_for_score(79.2) == "decent"
    assert scoring.label_for_score(80.0) == "strong"
    assert scoring.label_for_score(64.8) == "watchlist"
    assert scoring.label_for_score(49.7) == "weak"
    assert scoring.label_for_score(None) is None


def test_horizon_score_applies_earnings_penalty_within_window():
    components = {name: 80.0 for name in [
        "trend_component", "short_momentum_component", "relative_strength_component_5d",
        "volume_behavior_component", "risk_component", "setup_component",
    ]}
    no_penalty = scoring.compute_horizon_scores(components, days_until_earnings=10, earnings_risk_unknown=False)
    with_penalty = scoring.compute_horizon_scores(components, days_until_earnings=3, earnings_risk_unknown=False)
    assert no_penalty["score_5d"] - with_penalty["score_5d"] == pytest.approx(20.0)
