"""Sector timing — synthetic only, no DB, no network.

The analysis asks the dimension the model deliberately ignores: which SECTOR to be in. The tests
here are the usual adversarial ones — each names the wrong-but-plausible implementation it rules
out. The load-bearing pair is causality (a predictor built only from the past) and the
non-overlapping hold schedule (the only honest independent count this study can produce).
"""
import numpy as np
import pytest

from src import research


def test_trailing_excess_uses_only_the_past():
    """Rewrite the future half of both series; the predictor over the first half must not move."""
    rng = np.random.default_rng(1)
    n = 200
    etf = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    spy = 100 * np.exp(np.cumsum(rng.normal(0, 0.008, n)))
    before = research.trailing_excess(etf, spy, 60)
    etf2, spy2 = etf.copy(), spy.copy()
    etf2[100:] *= 3.0
    spy2[100:] *= 0.2
    after = research.trailing_excess(etf2, spy2, 60)
    assert np.allclose(before[:100], after[:100], equal_nan=True)
    assert np.isnan(before[:60]).all(), "no value before a full lookback exists"


def test_daily_ic_is_plus_one_when_prediction_orders_the_outcome():
    pred = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert research.daily_cross_sectional_ic(pred, pred * 10) == pytest.approx(1.0)
    assert research.daily_cross_sectional_ic(pred, -pred) == pytest.approx(-1.0)


def test_daily_ic_refuses_tiny_or_degenerate_cross_sections():
    """Twelve sectors is already thin. A correlation on three points, or on a constant side, is
    arithmetic rather than evidence and must not enter the average as a real number."""
    assert research.daily_cross_sectional_ic(np.array([1., 2., 3.]), np.array([3., 2., 1.])) is None
    pred = np.array([1., 2., 3., 4., 5.])
    assert research.daily_cross_sectional_ic(pred, np.zeros(5)) is None
    pred_nan = np.array([1., np.nan, 3., np.nan, 5., np.nan])
    assert research.daily_cross_sectional_ic(pred_nan, pred_nan) is None


def test_hold_windows_do_not_overlap_and_pick_the_right_baskets():
    """The non-overlapping schedule is the only honest independent count this study can give; if
    windows overlapped the "n" would be inflated exactly like the daily IC's is."""
    dates = [f"D{i:03d}" for i in range(10)]
    pred = np.tile(np.array([1., 2., 3., 4., 5., 6.]), (10, 1))
    fwd = np.tile(np.array([-0.1, -0.05, 0.0, 0.05, 0.10, 0.20]), (10, 1))
    out = research.non_overlapping_top_k(dates, pred, fwd, horizon=4, k=2)
    starts = [w["date"] for w in out]
    assert starts == ["D000", "D004", "D008"], "windows must be spaced by the horizon"
    assert out[0]["top"] == pytest.approx((0.10 + 0.20) / 2)
    assert out[0]["bottom"] == pytest.approx((-0.1 - 0.05) / 2)


def test_hold_schedule_skips_days_with_too_few_sectors():
    dates = [f"D{i:03d}" for i in range(6)]
    pred = np.full((6, 6), np.nan)
    fwd = np.full((6, 6), np.nan)
    pred[3] = [1, 2, 3, 4, 5, 6]
    fwd[3] = [1, 2, 3, 4, 5, 6]
    out = research.non_overlapping_top_k(dates, pred, fwd, horizon=2, k=2)
    assert [w["date"] for w in out] == ["D003"]


def test_sector_etf_list_excludes_size_benchmarks():
    etfs = research.sector_etfs()
    assert "IJH" not in etfs and "IJR" not in etfs and "SPY" not in etfs
    assert "SMH" in etfs and "XLE" in etfs
