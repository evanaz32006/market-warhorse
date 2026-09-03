"""Portfolio backtest — synthetic only, no DB, no network.

The tests that matter here are the adversarial ones: a backtest that is subtly wrong produces a
beautiful equity curve rather than an error, which is the same failure shape as a lookahead leak.
Each test states the specific wrong-but-plausible implementation it exists to rule out.
"""
import numpy as np
import pandas as pd
import pytest

from src import backtest, research
from src.config import PARAMS


def _panel(dates, closes, opens=None, volumes=None, scores=None, benchmark="SPY",
           score_col="score_60d"):
    """Build a Panel by hand. `closes`/`opens` are {ticker: [px,...]} aligned to `dates`."""
    closes = {t: np.asarray(v, dtype=np.float64) for t, v in closes.items()}
    opens = {t: np.asarray(v, dtype=np.float64) for t, v in (opens or closes).items()}
    volumes = {t: np.asarray(v, dtype=np.float64)
               for t, v in (volumes or {t: [1e7] * len(dates) for t in closes}).items()}
    date_idx = {t: {d: i for i, d in enumerate(dates)} for t in closes}
    rows = []
    for d in dates:
        for t in closes:
            if t == benchmark:
                continue
            rows.append({"run_date": d, "ticker": t, "benchmark": benchmark,
                         "recovered": 0, "fundamentals_pit": 1,
                         score_col: (scores or {}).get(t, 50.0)})
    return research.Panel(frame=pd.DataFrame(rows), closes=closes, date_idx=date_idx,
                          benchmark_of={t: benchmark for t in closes}, calendar=list(dates),
                          opens=opens, volumes=volumes)


def _dates(n):
    return [f"D{i:04d}" for i in range(n)]


# ---------------------------------------------------------------------------
# The no-lookahead fill rule
# ---------------------------------------------------------------------------

def test_fill_uses_next_session_open_not_the_close_that_produced_the_score():
    """THE load-bearing test.

    Date D's close is an INPUT to date D's score, so filling at that same close means trading on a
    price you needed in order to make the decision. The difference is invisible in the output — both
    produce a plausible equity curve — so it is asserted directly.

    Construction: the open on D+1 is deliberately far from the close on D. Whichever price the
    simulator paid is then recoverable from the share count."""
    dates = _dates(6)
    # close on D0 = 100; open on D1 = 200 (a 2x gap that makes the fill price unambiguous)
    closes = {"AAA": [100, 200, 200, 200, 200, 200], "SPY": [100] * 6}
    opens = {"AAA": [100, 200, 200, 200, 200, 200], "SPY": [100] * 6}
    p = _panel(dates, closes, opens, scores={"AAA": 99.0})
    m, cd, ce, _ = backtest.run_single_backtest(
        p, {dates[0]}, top_n=1, hold_days=20, score_col="score_60d", charge_costs=False)
    # filled at D1's open of 200 with $100k -> 500 shares -> equity stays 100k, never doubles
    assert ce[-1] == pytest.approx(100_000.0), (
        "equity moved, which means the fill used D0's close of 100 and then marked at 200 - "
        "that is the lookahead this test exists to catch")


def test_no_fill_when_there_is_no_next_session():
    # A rebalance signalled on the final session cannot be executed; it must be skipped, not filled
    # at the same day's close.
    dates = _dates(3)
    p = _panel(dates, {"AAA": [10, 11, 12], "SPY": [100] * 3}, scores={"AAA": 99.0})
    m, cd, ce, _ = backtest.run_single_backtest(
        p, {dates[-1]}, top_n=1, hold_days=20, score_col="score_60d", charge_costs=False)
    assert m["n_rebalances"] == 0
    assert ce[-1] == pytest.approx(PARAMS["backtest_initial_equity"])


# ---------------------------------------------------------------------------
# Costs
# ---------------------------------------------------------------------------

def test_zero_turnover_means_exactly_zero_cost():
    # If nothing trades, no cost may appear. A cost model that leaks a charge into a static book
    # would make every strategy look worse in a way that is invisible against a benchmark.
    dates = _dates(8)
    p = _panel(dates, {"AAA": [50] * 8, "SPY": [100] * 8}, scores={"AAA": 99.0})
    m, _, ce, _ = backtest.run_single_backtest(
        p, set(), top_n=1, hold_days=20, score_col="score_60d", charge_costs=True)
    assert m["n_rebalances"] == 0
    assert m["total_cost_paid"] == 0.0
    assert ce[-1] == pytest.approx(PARAMS["backtest_initial_equity"])


def test_charging_costs_strictly_reduces_terminal_equity():
    """Cost-charged and cost-free runs must differ, and only in the expected direction. Equal curves
    would mean the cost model is wired up but never actually applied - a silent no-op."""
    dates = _dates(30)
    px = list(np.linspace(100, 130, 30))
    p = _panel(dates, {"AAA": px, "BBB": px, "SPY": [100] * 30},
               scores={"AAA": 99.0, "BBB": 98.0})
    reb = {dates[0], dates[10], dates[20]}
    free, _, ce_free, _ = backtest.run_single_backtest(
        p, reb, top_n=1, hold_days=10, score_col="score_60d", charge_costs=False)
    paid, _, ce_paid, _ = backtest.run_single_backtest(
        p, reb, top_n=1, hold_days=10, score_col="score_60d", charge_costs=True)
    assert paid["total_cost_paid"] > 0
    assert ce_paid[-1] < ce_free[-1], "costs were charged but did not reduce equity"


def test_spread_widens_as_liquidity_falls_and_unknown_liquidity_is_pessimistic():
    """Unknown liquidity must return the CAP, not the floor. Defaulting an unknown cost to 'cheap'
    silently flatters every thinly-traded name in the book."""
    mega = backtest.spread_bps(5_000e6)     # $5B/day
    thin = backtest.spread_bps(0.5e6)       # $500k/day
    assert mega < thin
    assert backtest.spread_bps(None) == PARAMS["backtest_spread_max_bps"]
    assert backtest.spread_bps(0) == PARAMS["backtest_spread_max_bps"]
    assert mega >= PARAMS["backtest_spread_min_bps"]


def test_impact_grows_with_participation_and_is_capped():
    small = backtest.impact_bps(1e4, 1e9)
    large = backtest.impact_bps(1e8, 1e9)
    assert large > small
    # beyond the participation cap the modelled impact stops growing (the honest reading past that
    # point is "this trade does not happen", not "it costs a bit more")
    capped_a = backtest.impact_bps(5e8, 1e9)
    capped_b = backtest.impact_bps(9e9, 1e9)
    assert capped_a == pytest.approx(capped_b)


# ---------------------------------------------------------------------------
# Delisting / missing data
# ---------------------------------------------------------------------------

def test_holding_whose_series_ends_is_liquidated_at_its_last_real_price_and_flagged():
    """A name that stops trading mid-hold must be realized at a real historical close and COUNTED.
    Silently dropping it is the optimistic assumption: the position quietly disappears and the rest
    of the book carries the return as if the loss never happened."""
    dates = _dates(6)
    # AAA has prices only for the first 3 sessions
    closes = {"AAA": [100, 90, 80], "SPY": [100] * 6}
    date_idx = {"AAA": {d: i for i, d in enumerate(dates[:3])},
                "SPY": {d: i for i, d in enumerate(dates)}}
    rows = [{"run_date": d, "ticker": "AAA", "benchmark": "SPY", "recovered": 0,
             "fundamentals_pit": 1, "score_60d": 99.0} for d in dates]
    p = research.Panel(
        frame=pd.DataFrame(rows),
        closes={t: np.asarray(v, dtype=float) for t, v in closes.items()},
        date_idx=date_idx, benchmark_of={"AAA": "SPY"}, calendar=dates,
        opens={t: np.asarray(v, dtype=float) for t, v in closes.items()},
        volumes={t: np.asarray([1e7] * len(v), dtype=float) for t, v in closes.items()})
    m, cd, ce, diag = backtest.run_single_backtest(
        p, {dates[0], dates[4]}, top_n=1, hold_days=4, score_col="score_60d", charge_costs=False)
    # the loss from 100 -> 80 must be realized, not erased
    assert ce[-1] < PARAMS["backtest_initial_equity"]
    assert m["n_liquidated_missing"] >= 1, "a vanished holding was not flagged"


def test_suspicious_single_day_move_is_flagged():
    """A >50% one-day move with no corporate action is almost certainly an unadjusted split in the
    cache. It must be surfaced rather than compounded into the curve as a real return."""
    dates = _dates(5)
    closes = {"AAA": [100, 100, 300, 300, 300], "SPY": [100] * 5}   # 3x overnight
    p = _panel(dates, closes, scores={"AAA": 99.0})
    m, _, _, diag = backtest.run_single_backtest(
        p, {dates[0]}, top_n=1, hold_days=20, score_col="score_60d", charge_costs=False)
    assert m["n_suspicious_moves"] >= 1
    assert diag["suspicious"][0][1] == "AAA"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def test_equity_metrics_against_hand_computed_values():
    # doubling over exactly one trading year is a 100% CAGR; the drawdown is the trough vs the peak
    eq = [100.0] * 1 + [200.0] * (PARAMS["trading_days_per_year"])
    m = backtest.equity_metrics(eq)
    assert m["total_return"] == pytest.approx(1.0)
    assert m["cagr"] == pytest.approx(1.0, rel=0.02)

    drop = backtest.equity_metrics([100.0, 120.0, 60.0, 90.0])
    assert drop["max_drawdown_pct"] == pytest.approx(-50.0)     # 120 -> 60


def test_metrics_refuse_to_report_on_a_degenerate_curve():
    for bad in ([], [100.0], [0.0, 100.0]):
        m = backtest.equity_metrics(bad)
        assert m["cagr"] is None and m["sharpe"] is None


def test_buy_and_hold_benchmark_uses_the_same_session_grid():
    """The benchmark must be measured over the strategy's own dates. A curve computed on a different
    window is not a benchmark, it is a different experiment."""
    dates = _dates(5)
    p = _panel(dates, {"AAA": [10] * 5, "SPY": [100, 110, 120, 130, 140]}, scores={"AAA": 99.0})
    curve = backtest.buy_and_hold_curve(p, "SPY", dates)
    assert len(curve) == len(dates)
    assert curve[-1] / curve[0] == pytest.approx(140 / 100)


def test_rebalance_schedule_counts_trading_sessions_not_calendar_days():
    cal = _dates(100)
    sched = backtest.rebalance_schedule(cal, set(cal), hold_days=20)
    assert sched[0] == cal[0]
    assert sched[1] == cal[20]          # 20 SESSIONS later, holidays cannot shorten the hold
    assert len(sched) == 5


def test_rebalance_schedule_skips_dates_with_no_scored_cross_section():
    cal = _dates(40)
    scored = set(cal[10:])              # the first ten sessions have no snapshots
    sched = backtest.rebalance_schedule(cal, scored, hold_days=10)
    assert sched[0] == cal[10]
    assert all(d in scored for d in sched)
