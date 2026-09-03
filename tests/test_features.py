"""Stage 1 proof tests:
1. Hand-computed checks against known values for SMA, returns, ATR, max drawdown.
2. The structural no-lookahead proof: feeding rows *after* as_of_date must never change
   the computed result for as_of_date.
3. A sanity check that relative_strength = stock_return - benchmark_return.
"""

import numpy as np
import pandas as pd
import pytest

from src import features
from src.config import PARAMS


def _df(dates, opens, highs, lows, closes, volumes):
    return pd.DataFrame({
        "date": dates, "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes,
    })


def _date_range(n, start="2024-01-01"):
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, periods=n)]


# ---------------------------------------------------------------------------
# 1. Hand-computed unit tests
# ---------------------------------------------------------------------------

def test_sma20_matches_manual_average():
    closes = list(range(10, 30))  # 20 values: 10..29, mean = 19.5
    dates = _date_range(len(closes))
    df = _df(dates, closes, closes, closes, closes, [1_000_000] * len(closes))
    out = features._trend_features(df, PARAMS)
    assert out["SMA20"] == pytest.approx(19.5)


def test_return_5d_matches_known_ratio():
    closes = [100, 100, 100, 100, 100, 105]  # n=6 > 5d window
    dates = _date_range(len(closes))
    df = _df(dates, closes, closes, closes, closes, [1_000_000] * len(closes))
    out = features._return_features(df, PARAMS)
    assert out["return_5d"] == pytest.approx(0.05)


def test_return_252d_missing_when_insufficient_history():
    closes = [100] * 10
    dates = _date_range(len(closes))
    df = _df(dates, closes, closes, closes, closes, [1_000_000] * len(closes))
    out = features._return_features(df, PARAMS)
    assert out["return_252d"] is None
    assert out["return_252d_missing"] is True


def test_atr14_hand_computed_example():
    # 15 sessions: day0 has no prior close so TR0 falls back to high-low.
    # Days 1..14 (14 sessions) all have TR = 2.0 by construction (high-low=2, and the
    # close/prev_close gaps are smaller than 2), so ATR14 (mean of the last 14 TR values) = 2.0.
    n = 15
    highs = [101.0] + [102.0 + i for i in range(n - 1)]
    lows = [99.0] + [100.0 + i for i in range(n - 1)]
    closes = [100.0] + [101.0 + i for i in range(n - 1)]
    dates = _date_range(n)
    df = _df(dates, closes, highs, lows, closes, [1_000_000] * n)
    out = features._risk_features(df, PARAMS)
    assert out["ATR14"] == pytest.approx(2.0)


def test_max_drawdown_known_sequence():
    # Peak 110 at index1, trough 80 at index4 -> drawdown magnitude = (110-80)/110*100 = 27.2727...
    closes = pd.Series([100.0, 110.0, 90.0, 95.0, 80.0, 120.0])
    dd = features._max_drawdown_pct(closes)
    assert dd == pytest.approx(27.272727, rel=1e-4)


# ---------------------------------------------------------------------------
# 2. No-lookahead structural proof + 3. relative strength sanity check
# ---------------------------------------------------------------------------

def _synthetic_series(n, base=100.0, trend=0.3, amplitude=5.0, phase=0.0, vol_base=1_000_000.0):
    i = np.arange(n)
    close = base + trend * i + amplitude * np.sin(i / 10.0 + phase)
    high = close * 1.01
    low = close * 0.99
    open_ = close
    volume = vol_base + (i % 7) * 50_000.0
    dates = _date_range(n)
    return _df(dates, open_, high, low, close, volume)


@pytest.fixture
def long_ticker_and_benchmark():
    n = 300  # enough bars for every window up to return_252d
    ticker_df = _synthetic_series(n, base=100.0, trend=0.30, amplitude=5.0, phase=0.0)
    benchmark_df = _synthetic_series(n, base=50.0, trend=0.10, amplitude=2.0, phase=1.0)
    return ticker_df, benchmark_df


def test_no_lookahead_future_rows_do_not_change_result(long_ticker_and_benchmark):
    ticker_df, benchmark_df = long_ticker_and_benchmark
    as_of_date = ticker_df["date"].iloc[250]  # 50 future rows exist past this date in the full frame

    truncated_ticker = ticker_df[ticker_df["date"] <= as_of_date].reset_index(drop=True)
    truncated_benchmark = benchmark_df[benchmark_df["date"] <= as_of_date].reset_index(drop=True)

    result_with_future_rows = features.compute_features("TICK", "BENCH", as_of_date, ticker_df, benchmark_df)
    result_truncated_only = features.compute_features("TICK", "BENCH", as_of_date, truncated_ticker, truncated_benchmark)

    assert result_with_future_rows == result_truncated_only


def test_relative_strength_equals_stock_minus_benchmark_return(long_ticker_and_benchmark):
    ticker_df, benchmark_df = long_ticker_and_benchmark
    as_of_date = ticker_df["date"].iloc[280]

    out = features.compute_features("TICK", "BENCH", as_of_date, ticker_df, benchmark_df)

    for w in PARAMS["rs_windows"]:
        stock_ret = out[f"return_{w}d"]
        bench_ret = out[f"benchmark_return_{w}d"]
        rs = out[f"relative_strength_{w}d"]
        assert rs == pytest.approx(stock_ret - bench_ret)


def test_full_feature_set_has_no_nan_with_sufficient_history(long_ticker_and_benchmark):
    ticker_df, benchmark_df = long_ticker_and_benchmark
    as_of_date = ticker_df["date"].iloc[280]  # >252 bars available, every window should resolve

    out = features.compute_features("TICK", "BENCH", as_of_date, ticker_df, benchmark_df)

    for key, value in out.items():
        if key.endswith("_missing"):
            continue
        assert value is not None, f"{key} unexpectedly None with sufficient history"
        if isinstance(value, float):
            assert not np.isnan(value), f"{key} is NaN with sufficient history"
