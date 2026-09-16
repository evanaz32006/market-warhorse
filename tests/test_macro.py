"""Macro / regime data — synthetic only, no network.

Macro is the one roadmap source that is BACKFILLABLE, which makes it the one that can be tested
now rather than in six months. It is also the one carrying the nastiest lookahead trap, because
the leak is in the SOURCE rather than in the code: FRED serves the latest REVISED value for every
past date, so an economic statistic would hand the backtest numbers nobody had at the time.

Three things are load-bearing and each is tested against the wrong-but-plausible implementation:
  1. only market-priced (never-revised) series may be ingested at all;
  2. a regime threshold must be an EXPANDING quantile, never a full-sample one;
  3. a stale reading goes missing rather than being carried forward as current.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import macro


def _history(rows):
    return pd.DataFrame(rows, columns=["series_id", "date", "value"])


def _series(series_id, start_day, values):
    return [{"series_id": series_id, "date": "2024-01-%02d" % (start_day + i), "value": v}
            for i, v in enumerate(values)]


# ---------------------------------------------------------------------------
# 1. The revision guard
# ---------------------------------------------------------------------------

def test_only_market_priced_series_can_be_ingested():
    """THE structural guard. GDP/UNRATE/CPI/PAYEMS are all revised for years after first release;
    ingesting one would backfill numbers nobody had and produce a beautiful false result.

    The mutation this kills: dropping assert_market_priced from fetch_series."""
    for statistic in ("GDP", "UNRATE", "CPIAUCSL", "PAYEMS", "INDPRO"):
        with pytest.raises(ValueError, match="market-priced"):
            macro.assert_market_priced(statistic)
    for priced in ("VIXCLS", "T10Y2Y", "DGS10"):
        assert macro.assert_market_priced(priced) is True


def test_every_configured_series_records_why_it_is_revision_safe():
    """The justification is the thing a future addition is most likely to skip."""
    for sid, spec in macro.MACRO_SERIES.items():
        assert spec.get("why_safe"), f"{sid} has no recorded reason it is safe from revision"
        assert spec.get("label")


def test_fetch_series_refuses_a_statistic_before_making_any_request(monkeypatch):
    called = []
    monkeypatch.setattr(macro.requests, "get", lambda *a, **k: called.append(1))
    with pytest.raises(ValueError):
        macro.fetch_series("UNRATE")
    assert not called, "a refused series must not reach the network at all"


# ---------------------------------------------------------------------------
# 2. The expanding-quantile guard
# ---------------------------------------------------------------------------

def test_expanding_percentile_uses_only_the_past():
    """Rewrite the future half; the percentiles over the first half must not move. This is the
    mutation that matters: a full-sample quantile would label 2024 using 2026's distribution."""
    rng = np.random.default_rng(0)
    vals = rng.normal(20, 5, 600)
    before = macro.expanding_percentile(vals, min_history=50)
    vals2 = vals.copy()
    vals2[300:] *= 10
    after = macro.expanding_percentile(vals2, min_history=50)
    assert np.allclose(before[:300], after[:300], equal_nan=True)


def test_expanding_percentile_is_undefined_until_enough_history():
    vals = np.arange(100, dtype=float)
    out = macro.expanding_percentile(vals, min_history=30)
    assert np.isnan(out[:29]).all(), "a regime label on a handful of points is noise"
    assert not np.isnan(out[29:]).any()


def test_expanding_percentile_ranks_within_history_not_the_whole_series():
    """A rising series: each new high is the highest SO FAR, so its causal percentile is ~100 even
    though against the full sample most of them are low."""
    vals = np.arange(300, dtype=float)
    out = macro.expanding_percentile(vals, min_history=10)
    assert out[50] == pytest.approx(100.0 * 50 / 51, abs=0.1)
    assert out[-1] == pytest.approx(100.0 * 299 / 300, abs=0.1)


def test_expanding_percentile_tolerates_gaps():
    vals = np.array([1.0, np.nan, 3.0, 2.0, 5.0, np.nan, 4.0])
    out = macro.expanding_percentile(vals, min_history=3)
    assert np.isnan(out[5]), "a missing observation has no percentile"
    assert not np.isnan(out[4])


# ---------------------------------------------------------------------------
# 3. Staleness and the as-of gate
# ---------------------------------------------------------------------------

def test_as_of_value_never_reads_a_later_observation():
    hist = _history(_series("VIXCLS", 1, [10.0, 20.0, 30.0]))
    assert macro.as_of_value(hist, "VIXCLS", "2024-01-02")[0] == 20.0
    assert macro.as_of_value(hist, "VIXCLS", "2024-01-02", max_staleness_days=7)[0] == 20.0
    assert macro.as_of_value(hist, "VIXCLS", "2023-12-31")[0] is None


def test_a_stale_reading_goes_missing_rather_than_carrying_forward():
    """A series that stopped publishing must not keep supplying its last value as if it were
    current. The mutation this kills: returning the most recent row regardless of its age."""
    hist = _history(_series("VIXCLS", 1, [15.0]))
    fresh, age = macro.as_of_value(hist, "VIXCLS", "2024-01-05", max_staleness_days=7)
    assert fresh == 15.0 and age == 4
    stale, age = macro.as_of_value(hist, "VIXCLS", "2024-03-01", max_staleness_days=7)
    assert stale is None, "a two-month-old reading was presented as current"
    assert age == 60, "the age must still be reported so the reason is visible"


def test_missing_is_flagged_not_zeroed():
    hist = _history(_series("VIXCLS", 1, [15.0, 16.0]))
    feats = macro.macro_features_as_of(hist, "2024-01-02")
    assert feats["vix"] == 16.0
    assert feats["vix_missing"] is False
    # a series with no observations at all
    assert feats["yield_curve_10y2y"] is None
    assert feats["yield_curve_10y2y_missing"] is True
    assert feats["yield_curve_10y2y_pctile"] is None


def test_percentile_in_features_is_undefined_without_enough_history():
    """Two observations cannot define a regime, and must not pretend to."""
    hist = _history(_series("VIXCLS", 1, [15.0, 16.0]))
    assert macro.macro_features_as_of(hist, "2024-01-02")["vix_pctile"] is None


def test_regime_frame_is_date_sorted_and_causal():
    hist = _history([
        {"series_id": "VIXCLS", "date": "2024-01-03", "value": 30.0},
        {"series_id": "VIXCLS", "date": "2024-01-01", "value": 10.0},
        {"series_id": "VIXCLS", "date": "2024-01-02", "value": 20.0},
    ])
    frame = macro.regime_frame(hist, "VIXCLS")
    assert list(frame["date"]) == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert list(frame["value"]) == [10.0, 20.0, 30.0]


def test_fetch_series_drops_non_observations_rather_than_filling_them(monkeypatch):
    """FRED writes '.' for a day a series did not publish. Forward-filling one would invent a
    market price on a day that had none."""
    csv = "observation_date,VIXCLS\n2024-01-01,15.0\n2024-01-02,.\n2024-01-03,17.0\n"

    class _R:
        status_code = 200
        text = csv

        def raise_for_status(self):
            pass

    monkeypatch.setattr(macro.requests, "get", lambda *a, **k: _R())
    out = macro.fetch_series("VIXCLS")
    assert list(out["date"]) == ["2024-01-01", "2024-01-03"]
    assert list(out["value"]) == [15.0, 17.0]


# ---------------------------------------------------------------------------
# Macro must not become a ranking feature
# ---------------------------------------------------------------------------

def test_macro_is_not_wired_into_any_score():
    """A macro value is identical for every name on a date, so it CANNOT change a cross-sectional
    rank — including one would add a column that looks informative while being arithmetically
    incapable of doing anything. Macro is for conditioning and timing.

    The mutation this kills: adding a macro field to the scored columns or a weight map."""
    from src import storage
    from src.config import SCORE_WEIGHTS_BY_VERSION
    labels = [spec["label"] for spec in macro.MACRO_SERIES.values()]
    for col in storage.RAW_FEATURE_COLUMNS + storage.SCORE_COLUMNS + storage.PERCENTILE_COLUMNS:
        for label in labels:
            assert label not in col, f"{col} put a market-wide macro value into the cross-section"
    for weights in SCORE_WEIGHTS_BY_VERSION.values():
        for comp in weights:
            assert not any(l in comp for l in labels)


def test_every_series_records_how_deep_its_history_actually_is():
    """Two of the five are licensed and serve only ~3 years through the free endpoint, so their
    expanding percentile means "against the last 3 years" while the others mean "against decades".
    The numbers look identical, so the difference has to be written down or it gets forgotten."""
    for sid, spec in macro.MACRO_SERIES.items():
        assert spec.get("depth"), f"{sid} does not record how much history is actually available"
