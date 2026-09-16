"""Regime timing — aligning macro state to a price calendar. Synthetic only, no network.

This asks whether macro regime predicts the INDEX's own forward return, which is the question the
available data can actually answer: the snapshots begin 2024-06, so a regime-conditional test on
the MODEL's edge would leave about one independent 120-day window per bucket, while SPY's own
history gives ~70.

The alignment is where a leak would hide. A macro reading published on Tuesday must not label
Monday, and a regime label must never be cut against a distribution that includes the future.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import research


def _hist(rows):
    return pd.DataFrame(rows, columns=["series_id", "date", "value"])


def _vix(pairs):
    return _hist([{"series_id": "VIXCLS", "date": d, "value": v} for d, v in pairs])


# ---------------------------------------------------------------------------
# As-of alignment
# ---------------------------------------------------------------------------

def test_alignment_never_uses_a_macro_reading_published_after_the_date():
    """The mutation this kills: nearest-neighbour alignment, which would let Tuesday's VIX label
    Monday — a one-day leak that is invisible in any summary statistic."""
    hist = _vix([("2024-01-01", 10.0), ("2024-01-05", 99.0)])
    dates = ["2024-01-02", "2024-01-05"]
    out = research.macro_aligned_level(hist, "VIXCLS", dates, max_staleness_days=30)
    assert out[0] == 10.0, "a later observation leaked backwards"
    assert out[1] == 99.0


def test_alignment_refuses_a_reading_older_than_the_staleness_cap():
    """A dead series must go missing, not keep supplying its last value as if it were current."""
    hist = _vix([("2024-01-01", 10.0)])
    out = research.macro_aligned_level(hist, "VIXCLS", ["2024-01-03", "2024-03-01"],
                                       max_staleness_days=7)
    assert out[0] == 10.0
    assert np.isnan(out[1])


def test_alignment_before_any_observation_is_nan_not_the_first_value():
    hist = _vix([("2024-06-01", 10.0)])
    out = research.macro_aligned_level(hist, "VIXCLS", ["2024-01-01"], max_staleness_days=7)
    assert np.isnan(out[0])


def test_aligned_percentile_is_causal():
    """Rewrite the future; percentiles over the early dates must not move."""
    early = [("2024-%02d-01" % m, float(m)) for m in range(1, 13)]
    late = [("2025-%02d-01" % m, float(m)) for m in range(1, 13)]
    dates = [d for d, _ in early]
    a = research.macro_aligned_percentile(_hist(
        [{"series_id": "VIXCLS", "date": d, "value": v} for d, v in early + late]),
        "VIXCLS", dates, max_staleness_days=400)
    b = research.macro_aligned_percentile(_hist(
        [{"series_id": "VIXCLS", "date": d, "value": v * 100} for d, v in late]
        + [{"series_id": "VIXCLS", "date": d, "value": v} for d, v in early]),
        "VIXCLS", dates, max_staleness_days=400)
    assert np.allclose(a, b, equal_nan=True)


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def _long_vix(n=600, start=1):
    """A long enough series that the 252-observation minimum for a regime label is satisfied."""
    rows, d = [], pd.Timestamp("2020-01-01")
    for i in range(n):
        rows.append({"series_id": "VIXCLS", "date": (d + pd.Timedelta(days=i)).date().isoformat(),
                     "value": float(10 + (i % 40))})
    return pd.DataFrame(rows, columns=["series_id", "date", "value"])


def test_a_date_with_no_macro_reading_is_in_no_regime_condition():
    """A missing reading is not a regime. The mutation this kills: letting NaN fall into the LOW
    bucket via a naive `pct <= 33.3`, which would silently label every gap as calm."""
    hist = _long_vix()
    dates = ["2019-01-01", "2019-06-01"]          # entirely before the series starts
    conds = {c.name: c.mask for c in research.regime_conditions(hist, dates)}
    assert not conds["vix_high"].any()
    assert not conds["vix_low"].any(), "an unobserved date was classified as a low-VIX regime"


def test_high_and_low_regimes_are_disjoint():
    hist = _long_vix()
    dates = list(hist["date"])
    conds = {c.name: c.mask for c in research.regime_conditions(hist, dates)}
    assert not (conds["vix_high"] & conds["vix_low"]).any()


def test_inverted_curve_is_defined_by_LEVEL_not_by_percentile():
    """Inversion is a fact about the economy, not about where today sits in its own history. A
    percentile-based version would call the flattest third of a normal decade "inverted"."""
    hist = _hist([{"series_id": "T10Y2Y", "date": "2024-01-0%d" % i, "value": v}
                  for i, v in enumerate([0.5, 0.2, -0.1, -0.3, 0.4], start=1)])
    dates = ["2024-01-0%d" % i for i in range(1, 6)]
    conds = {c.name: c.mask for c in research.regime_conditions(hist, dates)}
    assert list(conds["yield_curve_inverted"]) == [False, False, True, True, False]


def test_every_configured_series_produces_a_high_and_a_low_condition():
    from src import macro
    hist = _long_vix()
    names = {c.name for c in research.regime_conditions(hist, list(hist["date"]))}
    for spec in macro.MACRO_SERIES.values():
        assert "%s_high" % spec["label"] in names
        assert "%s_low" % spec["label"] in names
    assert "yield_curve_inverted" in names


def test_conditions_are_boolean_masks_the_pattern_harness_can_consume():
    """They are fed straight to patterns.run_family, which rotates the mask in its circular-shift
    null — so it must be a real boolean array of the panel's length, not an index list."""
    hist = _long_vix()
    dates = list(hist["date"])
    for c in research.regime_conditions(hist, dates):
        assert c.mask.dtype == bool
        assert len(c.mask) == len(dates)
