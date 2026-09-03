"""Stage 3 proof tests: forward-return resolution by real trading date (never row
position), the guardrail for horizons that haven't elapsed yet, the date-ordering sanity
assertion catching a deliberately corrupted series, and performance-review bucketing.
"""

import math

import pandas as pd
import pytest

from src import evaluation


def _ticker_index(dates, closes):
    return dates, closes, {d: i for i, d in enumerate(dates)}


def test_forward_return_matches_known_ratio_by_real_trading_date():
    dates = [f"2024-01-{d:02d}" for d in range(1, 11)]  # 10 sequential trading days
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    bench_dates = dates
    bench_closes = [200, 200, 200, 200, 200, 202, 202, 202, 202, 202]

    t_dates, t_closes, t_idx = _ticker_index(dates, closes)
    b_dates, b_closes, b_idx = _ticker_index(bench_dates, bench_closes)

    snapshot_date = dates[2]  # close=102, idx=2
    out = evaluation.compute_forward_returns(
        snapshot_date, t_dates, t_closes, t_idx, b_dates, b_closes, b_idx
    )

    expected_fut_ret = closes[7] / closes[2] - 1.0  # idx 2 + 5 = idx 7
    expected_bench_ret = bench_closes[7] / bench_closes[2] - 1.0
    assert out["future_return_5d"] == pytest.approx(expected_fut_ret)
    assert out["future_benchmark_return_5d"] == pytest.approx(expected_bench_ret)
    assert out["future_excess_return_5d"] == pytest.approx(expected_fut_ret - expected_bench_ret)


def test_forward_return_is_none_when_horizon_has_not_elapsed_yet():
    dates = [f"2024-01-{d:02d}" for d in range(1, 11)]
    closes = list(range(100, 110))
    t_dates, t_closes, t_idx = _ticker_index(dates, closes)
    b_dates, b_closes, b_idx = _ticker_index(dates, closes)

    snapshot_date = dates[8]  # only 1 trading day remains -> 5d/20d/60d/120d all unresolved
    out = evaluation.compute_forward_returns(
        snapshot_date, t_dates, t_closes, t_idx, b_dates, b_closes, b_idx
    )
    assert out["future_return_5d"] is None
    assert out["future_excess_return_5d"] is None
    assert out["future_return_120d"] is None


def test_date_join_bug_raises_instead_of_silently_returning_a_wrong_number():
    # Deliberately shuffled: ticker_dates[idx+5] resolves to a date BEFORE snapshot_date,
    # simulating a row-position join bug. Must raise, never silently return a number.
    ticker_dates = ["2024-01-10", "2024-01-02", "2024-01-03", "2024-01-04",
                     "2024-01-05", "2024-01-01", "2024-01-07", "2024-01-08",
                     "2024-01-09", "2024-01-11"]
    ticker_closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    t_dates, t_closes, t_idx = _ticker_index(ticker_dates, ticker_closes)

    snapshot_date = ticker_dates[0]  # "2024-01-10"
    with pytest.raises(ValueError):
        evaluation.compute_forward_returns(
            snapshot_date, t_dates, t_closes, t_idx, t_dates, t_closes, t_idx
        )


def test_build_performance_review_buckets_by_label_and_computes_known_hit_rate():
    evaluated_rows = [
        {"score_20d": 85, "future_excess_return_20d": 0.05, "max_drawdown_after_20d": 2.0},
        {"score_20d": 90, "future_excess_return_20d": -0.02, "max_drawdown_after_20d": 3.0},
        {"score_20d": 55, "future_excess_return_20d": 0.01, "max_drawdown_after_20d": 1.0},
        {"score_20d": 30, "future_excess_return_20d": -0.03, "max_drawdown_after_20d": 4.0},
    ]
    review = evaluation.build_performance_review(evaluated_rows)
    buckets = review[review["report_type"] == "bucket"].set_index("label")

    strong = buckets.loc["strong"]
    assert strong["n"] == 2
    assert strong["avg_future_excess_return"] == pytest.approx(0.015)
    assert strong["hit_rate_pct"] == pytest.approx(50.0)
    assert strong["avg_max_drawdown_after"] == pytest.approx(2.5)

    watchlist = buckets.loc["watchlist"]
    assert watchlist["n"] == 1
    assert watchlist["hit_rate_pct"] == pytest.approx(100.0)

    weak = buckets.loc["weak"]
    assert weak["n"] == 1
    assert weak["hit_rate_pct"] == pytest.approx(0.0)


# --------------------------------------------------------------------------------------------
# Cross-sectional decile / top-N metrics (Job 2a)
# --------------------------------------------------------------------------------------------

def _drow(run_date, ticker, score, excess, horizon=20, **kw):
    r = {"run_date": run_date, "ticker": ticker, "benchmark": "SPY", "model_version": "vX",
         f"score_{horizon}d": score, f"future_excess_return_{horizon}d": excess,
         f"max_drawdown_after_{horizon}d": 5.0}
    r.update(kw)
    return r


def _report(rows, rtype):
    df = evaluation.build_performance_review(rows, model_version="vX")
    return df[df["report_type"] == rtype]


def test_deciles_are_assigned_within_day_not_pooled():
    """Day A's scores are all higher than day B's. Pooled ranking would put every day-B name in the
    bottom decile; per-day ranking gives each day its own full 1..10 spread. Pooling would also mix
    regimes, which is the same defect the fixed 80/65/50 score bands already have."""
    rows = ([_drow("2025-01-02", f"A{i}", 90 + i * 0.1, 0.01) for i in range(40)]
            + [_drow("2025-01-03", f"B{i}", 1 + i * 0.1, 0.01) for i in range(40)])
    dec = evaluation.build_decile_report(pd.DataFrame(rows), "vX", horizons=(20,))
    per_decile = [r for r in dec if r["report_type"] == "decile"]
    # both days contribute to decile 1 -> 2 contributing days, not 1
    d1 = next(r for r in per_decile if r["decile"] == 1)
    assert d1["n_days"] == 2


def test_ties_share_a_decile():
    scores = pd.Series([50.0] * 20 + list(range(60, 80)))
    d = evaluation.assign_deciles(scores, n_buckets=10)
    tied = d.iloc[:20]
    assert tied.nunique() == 1                 # the 20 identical scores land in ONE decile
    assert d.notna().all()


def test_all_tied_day_is_counted_not_crashed():
    # Every score identical: no ordering exists, so the day contributes no spread but IS recorded.
    rows = [_drow("2025-01-02", f"T{i}", 50.0, (i - 20) / 100.0) for i in range(40)]
    spread = _report(rows, "decile_spread")
    r = spread[spread["horizon"] == "20d"].iloc[0]
    assert r["days_skipped_degenerate_ties"] == 1
    assert r["n_days"] == 0                    # no spread observation from a day with no ordering


def test_empty_decile_contributes_no_observation_not_a_zero():
    """THE most likely silent bug here. Day 1's ties leave some deciles empty; day 2 is fully spread.
    An empty decile must contribute NOTHING — recording it as 0.0 would drag the cross-day average
    toward zero and invent an observation that never happened (invariant #2)."""
    day1 = [_drow("2025-01-02", f"A{i}", 50.0 if i < 35 else 99.0, 0.20) for i in range(40)]
    day2 = [_drow("2025-01-03", f"B{i}", float(i), 0.10) for i in range(40)]
    dec = evaluation.build_decile_report(pd.DataFrame(day1 + day2), "vX", horizons=(20,))
    per_decile = {r["decile"]: r for r in dec if r["report_type"] == "decile"}
    for d, row in per_decile.items():
        # every recorded decile average must equal one of the real daily values (0.20 / 0.10 / their
        # mean), never something pulled toward 0 by a phantom empty-bucket zero
        assert row["avg_future_excess_return"] >= 0.10 - 1e-9, (d, row)


def test_spread_is_mean_of_daily_spreads_not_pooled():
    """A 40-name day and a 200-name day with different spreads must count EQUALLY. Pooling rows would
    let the big day dominate — and this universe grew 58 -> 519 names, so pooling would silently
    weight recent years several times more heavily than early ones."""
    small = [_drow("2025-01-02", f"S{i}", float(i), 0.50 if i >= 36 else (-0.50 if i < 4 else 0.0))
             for i in range(40)]
    big = [_drow("2025-01-03", f"B{i}", float(i), 0.10 if i >= 180 else (-0.10 if i < 20 else 0.0))
           for i in range(200)]
    spread = _report(small + big, "decile_spread")
    r = spread[spread["horizon"] == "20d"].iloc[0]
    assert r["n_days"] == 2
    # daily spreads are 1.0 and 0.2 -> unweighted mean 0.6; a row-weighted mean would be ~0.33
    assert abs(r["spread_avg"] - 0.6) < 0.02


def test_days_below_min_names_are_excluded():
    rows = ([_drow("2025-01-02", f"A{i}", float(i), 0.01) for i in range(12)]      # too few names
            + [_drow("2025-01-03", f"B{i}", float(i), 0.01) for i in range(40)])
    spread = _report(rows, "decile_spread")
    r = spread[spread["horizon"] == "20d"].iloc[0]
    assert r["days_considered"] == 1              # only the 40-name day qualified


def test_top_n_includes_all_tied_names_at_the_boundary():
    # 12 names tied for the 10th slot: all are included and `avg_names_per_day` says so truthfully.
    rows = [_drow("2025-01-02", f"T{i}", 99.0 if i < 12 else float(i), 0.05) for i in range(40)]
    sel = _report(rows, "selection")
    r = sel[(sel["horizon"] == "20d") & (sel["selection"] == "top_10")].iloc[0]
    assert r["avg_names_per_day"] == 12.0


def test_top_n_reports_excess_versus_the_universe_not_just_zero():
    # In a tape where EVERY name is up, a top-N book can post a positive return and still trail the
    # universe it was picked from. The honest benchmark is that day's universe mean.
    rows = [_drow("2025-01-02", f"T{i}", float(i), 0.10 if i < 30 else 0.02) for i in range(40)]
    sel = _report(rows, "selection")
    r = sel[(sel["horizon"] == "20d") & (sel["selection"] == "top_10")].iloc[0]
    assert r["avg_future_excess_return"] > 0        # positive in absolute terms
    assert r["avg_excess_vs_universe"] < 0          # but WORSE than the universe it came from


def test_decile_report_absent_when_run_date_missing():
    # Legacy sparse-row-dict callers (the pre-existing tests) must keep working unchanged.
    rows = [{"score_20d": 85, "future_excess_return_20d": 0.05, "max_drawdown_after_20d": 3.0}]
    df = evaluation.build_performance_review(rows, model_version="vX")
    assert set(df["report_type"]) <= {"bucket", "component_correlation"}


def test_decile_excludes_rows_with_stale_fundamentals():
    # Composite-score metrics use the shared has_stale_fundamentals rule, exactly as the journal's
    # cohort grading does — a stale-fundamentals row's composite is not a real PIT prediction.
    good = [_drow("2025-01-02", f"G{i}", float(i), 0.01, recovered=0) for i in range(40)]
    stale = [_drow("2025-01-03", f"S{i}", float(i), 0.01, recovered=1) for i in range(40)]
    spread = _report(good + stale, "decile_spread")
    r = spread[spread["horizon"] == "20d"].iloc[0]
    assert r["days_considered"] == 1              # the recovered day is dropped entirely


def test_overlap_adjusted_t_uses_effective_sample_size():
    """250 daily snapshots of a 250-day forward return contain ~1 independent observation, not 250.
    The naive t would be ~sqrt(250) = 16x overstated."""
    naive = evaluation._overlap_adjusted_t(0.01, 0.1, 200, horizon=1)
    adjusted = evaluation._overlap_adjusted_t(0.01, 0.1, 200, horizon=20)
    assert abs(naive / adjusted - math.sqrt(20)) < 0.01
    assert evaluation._overlap_adjusted_t(0.01, None, 200, 20) is None
