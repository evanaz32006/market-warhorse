"""Sector timing on the full ETF history — synthetic only, no network.

Two things must hold. The long panel must never touch `price_history` or the SPY-derived master
calendar (it is a separate cache for one question). And a series that begins later than the
calendar — XLRE in 2015, XLC in 2018 — must be NaN before it exists, never forward-filled into
a fabricated flat line that would read as years of 0% days.
"""
import numpy as np
import pandas as pd
import pytest

from src import research


def _series(dates, start_at=0, base=100.0):
    return pd.Series([base + i for i in range(start_at, len(dates))], index=dates[start_at:])


def test_long_panel_aligns_to_the_calendar_and_leaves_pre_inception_nan():
    dates = [f"2000-01-{d:02d}" for d in range(1, 11)]
    series = {"SPY": _series(dates), "XLE": _series(dates), "XLRE": _series(dates, start_at=4)}
    panel = research.build_long_panel(series)
    assert panel.dates == dates
    assert np.isnan(panel.closes["XLRE"][:4]).all(), "must not fabricate bars before inception"
    assert not np.isnan(panel.closes["XLRE"][4:]).any()
    assert not np.isnan(panel.closes["XLE"]).any()


def test_long_panel_never_forward_fills_a_missing_session():
    dates = [f"2000-01-{d:02d}" for d in range(1, 8)]
    xle = _series(dates).drop(dates[3])          # one missing session in the middle
    panel = research.build_long_panel({"SPY": _series(dates), "XLE": xle})
    assert np.isnan(panel.closes["XLE"][3])
    assert panel.closes["XLE"][2] == 102.0 and panel.closes["XLE"][4] == 104.0


def test_long_panel_is_a_pattern_panel_so_forward_returns_is_reused():
    from src.patterns import PatternPanel, forward_returns
    dates = [f"2000-01-{d:02d}" for d in range(1, 8)]
    panel = research.build_long_panel({"SPY": _series(dates), "XLE": _series(dates, base=50.0)})
    assert isinstance(panel, PatternPanel)
    fwd = forward_returns(panel, "XLE", 2, benchmark="SPY")
    assert fwd[0] == pytest.approx((52 / 50 - 1) - (102 / 100 - 1))
    assert np.isnan(fwd[-2:]).all()


def test_chronological_halves_split_at_the_configured_fraction():
    from src.config import PARAMS
    a, b = research.chronological_halves(1000)
    cut = int(1000 * PARAMS["pattern_oos_split"])
    assert (a.start, a.stop) == (0, cut) and (b.start, b.stop) == (cut, 1000)
    a, b = research.chronological_halves(10, split=0.5)
    assert a.stop == 5 and b.start == 5


def test_cache_loader_reads_the_csv_without_a_network_call(tmp_path):
    path = tmp_path / "cache.csv"
    pd.DataFrame({"ticker": ["SPY", "SPY", "XLE"], "date": ["2000-01-03", "2000-01-04", "2000-01-03"],
                  "close": [100.0, 101.0, 50.0]}).to_csv(path, index=False)
    out = research.sector_long_history_cache(cache_path=str(path))
    assert list(out["SPY"].index) == ["2000-01-03", "2000-01-04"]
    assert out["XLE"].iloc[0] == 50.0
