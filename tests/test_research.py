"""Research analyses (Job 2b/2c) — synthetic only, no DB, no network.

The load-bearing test in this file is `test_walk_forward_weights_lag_a_known_ic_sign_flip`. Everything
else guards a specific arithmetic claim; that one guards the no-lookahead invariant, which is the one
failure this whole project exists to prevent.
"""
import numpy as np
import pandas as pd
import pytest

from src import evaluation, research


# ---------------------------------------------------------------------------
# Vectorized forward returns must match the scalar implementation exactly
# ---------------------------------------------------------------------------

def _panel(dates, closes_by_ticker, benchmark_of):
    closes = {t: np.asarray(c, dtype=np.float64) for t, c in closes_by_ticker.items()}
    date_idx = {t: {d: i for i, d in enumerate(dates)} for t in closes_by_ticker}
    return research.Panel(frame=pd.DataFrame(), closes=closes, date_idx=date_idx,
                          benchmark_of=benchmark_of, calendar=list(dates))


def test_forward_excess_vector_matches_scalar_forward_return():
    """The vectorized path and evaluation._forward_return must agree at EVERY horizon. They are two
    implementations of the same no-lookahead rule, and the fast one is only trustworthy while it is
    provably the same as the slow one."""
    dates = [f"2025-01-{i:02d}" for i in range(1, 21)]
    tc = [100 + i * 1.5 for i in range(20)]
    bc = [50 + i * 0.4 for i in range(20)]
    panel = _panel(dates, {"T": tc, "SPY": bc}, {"T": "SPY"})
    vec = research.forward_excess_vector("T", "SPY", dates[3], panel, max_h=19)
    for h in range(1, 17):
        t_ret = evaluation._forward_return(tc, 3, h)
        b_ret = evaluation._forward_return(bc, 3, h)
        assert abs(float(vec[h - 1]) - (t_ret - b_ret)) < 1e-6, h


def test_forward_excess_vector_guardrail_at_long_horizons():
    # A ticker with only 10 sessions has no h>=7 outcome from index 3. Those must be NaN — never 0.0,
    # which would enter the IC as "flat performance" for a period that has not happened.
    dates = [f"2025-01-{i:02d}" for i in range(1, 11)]
    panel = _panel(dates, {"T": [100 + i for i in range(10)], "SPY": [50 + i for i in range(10)]},
                   {"T": "SPY"})
    vec = research.forward_excess_vector("T", "SPY", dates[3], panel, max_h=20)
    assert not np.isnan(vec[:6]).any()      # h = 1..6 exist
    assert np.isnan(vec[6:]).all()          # h >= 7 do not


def test_forward_excess_vector_unknown_date_is_all_nan():
    dates = [f"2025-01-{i:02d}" for i in range(1, 11)]
    panel = _panel(dates, {"T": [100 + i for i in range(10)], "SPY": [50 + i for i in range(10)]},
                   {"T": "SPY"})
    assert np.isnan(research.forward_excess_vector("T", "SPY", "2030-01-01", panel, 5)).all()


# ---------------------------------------------------------------------------
# Maturity primitives
# ---------------------------------------------------------------------------

def test_maturity_date_resolves_and_guards():
    cal = [f"2025-01-{i:02d}" for i in range(1, 21)]
    assert evaluation.maturity_date(cal, "2025-01-01", 5) == "2025-01-06"
    assert evaluation.maturity_date(cal, "2025-01-19", 5) is None      # D+5 has not elapsed
    assert evaluation.maturity_date(cal, "1999-01-01", 5) is None      # not a session


def test_maturity_date_raises_on_a_corrupted_calendar():
    # Same protection as the forward-return date-join assertion: a calendar out of order must raise
    # rather than silently resolve a "future" date that is actually in the past.
    bad = ["2025-01-10", "2025-01-02", "2025-01-03"]
    with pytest.raises(ValueError):
        evaluation.maturity_date(bad, "2025-01-10", 1)


# ---------------------------------------------------------------------------
# Walk-forward schedule — pure date arithmetic, the place the lookahead rule lives
# ---------------------------------------------------------------------------

def _calendar(n=400):
    return [f"D{i:04d}" for i in range(n)]


def test_walk_forward_schedule_never_trains_past_its_cutoff():
    cal = _calendar()
    windows = research.walk_forward_schedule(cal, cal, horizon=20, min_dates=60, refit_every=21)
    assert windows
    for w in windows:
        assert max(w.train_dates) <= w.maturity_cutoff_date
        # the cutoff IS "horizon sessions before train_end" on the real calendar, not an approximation
        assert w.maturity_cutoff_date == cal[cal.index(w.train_end_date) - 20]
        assert min(w.oos_dates) > w.train_end_date


def test_fit_raises_if_training_frame_contains_immature_rows():
    """The structural assertion, tested directly. A caller that hand-builds a window with a training
    date past its cutoff must be refused, not quietly obliged."""
    cal = _calendar(200)
    cube = research.IcCube(ic=np.zeros((10, 1, 20), np.float32), n_obs=np.zeros((10, 1, 20), np.int32),
                           dates=cal[:10], series=["trend_component"], horizons=list(range(1, 21)))
    bad = research.TrainWindow(fit_seq=1, horizon=20, train_end_date=cal[50],
                               maturity_cutoff_date=cal[30],
                               train_dates=cal[:40],           # cal[31..39] are PAST the cutoff
                               oos_dates=cal[51:60])
    with pytest.raises(ValueError, match="lookahead"):
        research.fit_ic_weights(cube, bad, "ic_mean")


# ---------------------------------------------------------------------------
# THE adversarial lookahead test
# ---------------------------------------------------------------------------

def _flip_cube(calendar, horizon=20, flip=200, n_dates=400):
    """A cube whose trend IC is +1 for outcomes realized BEFORE the flip and -1 after.

    The IC is keyed on the date the outcome is REALIZED, which is the whole point: snapshots taken on
    D[181..199] already have flipped outcomes, because their 20-day return lands at or after D[200].
    Those 19 dates are the trap a `run_date <= T` implementation walks into."""
    series = ["trend_component", "relative_strength_component_20d"]
    ic = np.zeros((n_dates, len(series), horizon), np.float32)
    for di in range(n_dates):
        realized = di + horizon
        ic[di, 0, :] = 1.0 if realized < flip else -1.0     # the flipper
        ic[di, 1, :] = 0.5                                  # the constant
    return research.IcCube(ic=ic, n_obs=np.full((n_dates, len(series), horizon), 50, np.int32),
                           dates=calendar[:n_dates], series=series,
                           horizons=list(range(1, horizon + 1)))


def _naive_schedule(run_dates, calendar, horizon, window, min_dates, refit_every):
    """THE BUG THIS TEST EXISTS TO CATCH: a trailing window filtered on `run_date <= T` instead of on
    when each outcome became KNOWABLE. It reads as obviously correct and is not. Kept here so the
    test can prove it actually discriminates rather than merely passing."""
    out, seq = [], 0
    for i, T in enumerate(run_dates):
        eligible = run_dates[:i + 1][-window:]                  # <-- no maturity cutoff
        if len(eligible) < min_dates:
            continue
        if out and calendar.index(T) - calendar.index(out[-1].train_end_date) < refit_every:
            continue
        oos = run_dates[i + 1:i + 1 + refit_every]
        if not oos:
            continue
        seq += 1
        out.append(research.TrainWindow(seq, horizon, T, T, eligible, oos))
    return out


def _last_pre_flip_trend_weight(schedule, cube, cal, flip):
    """Trend's weight at the LAST fit trained entirely before the flip date.

    Late in the trap zone is where the two implementations diverge most: at train_end = D[199] a
    naive 40-date window is half-full of snapshots whose outcomes land after the flip, while a
    maturity-filtered window contains none of them. Probing early in the zone would find only a
    couple of contaminated dates and could not tell the implementations apart."""
    best = None
    for w in schedule:
        if cal.index(w.train_end_date) < flip:
            best = w
    weights, _ = research.fit_ic_weights(cube, best, "ic_mean")
    return weights["trend_component"], best


def test_walk_forward_weights_lag_a_known_ic_sign_flip():
    """A component's predictive sign flips at a known date. Correct walk-forward weights must:
      (a) NOT anticipate the flip — no weight change before the flipped outcomes were knowable;
      (b) FAIL for a naive `run_date <= T` filter, proven here by running that implementation
          side-by-side rather than asserting a threshold both would satisfy;
      (c) eventually react at all, so a stub returning a constant cannot pass;
      (d) satisfy the per-fit date invariants; and
      (e) never produce a negative weight.

    A ROLLING window is used deliberately. Under an expanding window the training set grows to 300+
    dates and the ~20 contaminated ones cannot move the mean enough to change any threshold crossing
    — both implementations would pass, and the test would be measuring dilution, not correctness.
    """
    H, FLIP, WINDOW = 20, 200, 40
    cal = _calendar(400)
    cube = _flip_cube(cal, horizon=H, flip=FLIP)
    windows = research.walk_forward_schedule(cal[:400], cal, horizon=H, mode="rolling",
                                             window=WINDOW, min_dates=30, refit_every=3)
    assert windows, "schedule produced no fits — the rest of this test would be vacuous"

    trend_weight = {}
    for w in windows:
        weights, _diag = research.fit_ic_weights(cube, w, "ic_mean")
        idx = cal.index(w.train_end_date)
        trend_weight[idx] = weights["trend_component"]

        # (d) per-fit structural invariants, checked on EVERY fit
        assert w.maturity_cutoff_date == cal[idx - H]
        assert max(w.train_dates) <= w.maturity_cutoff_date
        assert min(w.oos_dates) > w.train_end_date
        # (e) clipping, never inversion
        assert all(v >= 0 for v in weights.values())

        # (a) no anticipation: while every KNOWABLE outcome is still pre-flip, trend stays dominant
        if idx < FLIP:
            assert weights["trend_component"] > weights["relative_strength_component_20d"], (
                f"anticipated the flip at D[{idx}] — trend already lost dominance")

    # (b) THE MATURITY TRAP, proven by discrimination rather than by threshold. At the last pre-flip
    # fit, the correct implementation has seen NO flipped outcome (weight stays ~0.667), while the
    # naive one's window is already half-contaminated by snapshots whose returns land after the flip
    # and has collapsed (~0.167). This single comparison is what separates correct from subtly-wrong.
    correct_w, correct_fit = _last_pre_flip_trend_weight(windows, cube, cal, FLIP)
    naive = _naive_schedule(cal[:400], cal, H, WINDOW, 30, 3)
    naive_w, _naive_fit = _last_pre_flip_trend_weight(naive, cube, cal, FLIP)
    assert correct_w > 0.6, (
        f"maturity-filtered weights collapsed to {correct_w:.3f} at "
        f"{correct_fit.train_end_date}, before any flipped outcome was knowable")
    assert naive_w < 0.3, (
        "the naive run_date<=T implementation did NOT collapse, so this test cannot tell the two "
        "apart and proves nothing — fix the construction, not the assertion")
    assert correct_w > naive_w * 3

    # (c) the lag is real, not a freeze: it must eventually respond to the flip
    post_flip = [w for i, w in trend_weight.items() if i >= FLIP + H]
    assert post_flip and min(post_flip) < 0.10


def test_negative_ic_is_clipped_not_inverted():
    cal = _calendar(200)
    ic = np.zeros((100, 2, 20), np.float32)
    ic[:, 0, :] = -0.8                      # strongly negative
    ic[:, 1, :] = 0.4
    cube = research.IcCube(ic=ic, n_obs=np.full((100, 2, 20), 50, np.int32), dates=cal[:100],
                           series=["trend_component", "setup_component"],
                           horizons=list(range(1, 21)))
    w = research.TrainWindow(1, 20, cal[99], cal[99], cal[:100], cal[100:120])
    weights, diag = research.fit_ic_weights(cube, w, "ic_mean")
    assert weights["trend_component"] == 0.0                 # clipped to zero, never negative
    assert diag["diagnostics"]["trend_component"]["clipped"] is True
    assert weights["setup_component"] == pytest.approx(1.0)


def test_all_negative_falls_back_to_equal_weights_and_flags_it():
    cal = _calendar(200)
    ic = np.full((100, 2, 20), -0.5, np.float32)
    cube = research.IcCube(ic=ic, n_obs=np.full((100, 2, 20), 50, np.int32), dates=cal[:100],
                           series=["trend_component", "setup_component"],
                           horizons=list(range(1, 21)))
    w = research.TrainWindow(1, 20, cal[99], cal[99], cal[:100], cal[100:120])
    weights, diag = research.fit_ic_weights(cube, w, "ic_mean")
    assert diag["degenerate"] is True
    assert weights["trend_component"] == pytest.approx(0.5)
    # must NOT silently reinstate the hand-set config weights — that would disguise a failed fit
    from src.config import SCORE_WEIGHTS
    assert weights != SCORE_WEIGHTS.get("20d", {})


def test_component_below_min_ic_days_gets_zero_weight_and_is_flagged():
    cal = _calendar(200)
    ic = np.full((100, 2, 20), np.nan, np.float32)
    ic[:, 0, :] = 0.3                       # plenty of observations
    ic[:5, 1, :] = 0.9                      # only 5 days -> below wf_min_component_ic_days
    cube = research.IcCube(ic=ic, n_obs=np.full((100, 2, 20), 50, np.int32), dates=cal[:100],
                           series=["trend_component", "setup_component"],
                           horizons=list(range(1, 21)))
    w = research.TrainWindow(1, 20, cal[99], cal[99], cal[:100], cal[100:120])
    weights, diag = research.fit_ic_weights(cube, w, "ic_mean")
    assert weights["setup_component"] == 0.0
    assert diag["diagnostics"]["setup_component"]["unavailable"] is True   # flagged, never imputed


def test_ic_ratio_variant_uses_stability_not_just_level():
    """IC_Ratio should prefer a steady small IC over a wild large one; IC_Mean does the opposite.
    If both variants always agreed there would be no point reporting two."""
    cal = _calendar(200)
    rng = np.random.default_rng(0)
    ic = np.zeros((100, 2, 20), np.float32)
    ic[:, 0, :] = np.repeat((0.10 + rng.normal(0, 0.01, 100))[:, None], 20, axis=1)  # steady, small
    ic[:, 1, :] = np.repeat((0.14 + rng.normal(0, 0.40, 100))[:, None], 20, axis=1)  # bigger, wild
    cube = research.IcCube(ic=ic, n_obs=np.full((100, 2, 20), 50, np.int32), dates=cal[:100],
                           series=["trend_component", "setup_component"],
                           horizons=list(range(1, 21)))
    w = research.TrainWindow(1, 20, cal[99], cal[99], cal[:100], cal[100:120])
    by_mean, _ = research.fit_ic_weights(cube, w, "ic_mean")
    by_ratio, _ = research.fit_ic_weights(cube, w, "ic_ratio")
    assert by_mean["setup_component"] > by_mean["trend_component"]     # level favours the wild one
    assert by_ratio["trend_component"] > by_ratio["setup_component"]   # stability favours the steady one


# ---------------------------------------------------------------------------
# apply_weights must honour the production renormalization contract
# ---------------------------------------------------------------------------

def test_apply_weights_renormalizes_sitouts_and_nulls_on_missing_mandatory():
    frame = pd.DataFrame([
        {"trend_component": 80.0, "value_component": 40.0},   # both present
        {"trend_component": 80.0, "value_component": None},   # SITOUT missing -> renormalize
        {"trend_component": None, "value_component": 40.0},   # MANDATORY missing -> None
    ])
    out = research.apply_weights(frame, {"trend_component": 0.5, "value_component": 0.5})
    assert out.iloc[0] == pytest.approx(60.0)
    assert out.iloc[1] == pytest.approx(80.0)      # trend's weight renormalizes to 1
    assert pd.isna(out.iloc[2])                    # a mandatory component missing kills the score


# ---------------------------------------------------------------------------
# Quality decomposition
# ---------------------------------------------------------------------------

def test_quality_legs_track_the_composite_definition_and_signs():
    legs = dict(research.quality_legs())
    assert legs["profit_margin"] == 1.0
    assert legs["return_on_equity"] == 1.0
    # debt_to_equity is the INVERTED leg — lower leverage ranks better. If this sign is ever wrong,
    # the composite ranks the most-levered names as the highest quality.
    assert legs["debt_to_equity"] == -1.0
    from src.config import FUNDAMENTAL_PERCENTILE_GROUPS
    spec = FUNDAMENTAL_PERCENTILE_GROUPS["quality_percentile"]
    assert set(legs) == set(spec["fields"]) | set(spec["invert_fields"])   # cannot drift


# ---------------------------------------------------------------------------
# IC cube arithmetic
# ---------------------------------------------------------------------------

def test_ic_cube_matches_a_hand_computed_daily_spearman():
    dates = [f"2025-01-{i:02d}" for i in range(1, 15)]
    tickers = [f"T{i}" for i in range(5)]
    closes = {t: [100.0] * 14 for t in tickers}
    # ticker i gains i% over one session from index 0 -> a clean monotone cross-section
    for i, t in enumerate(tickers):
        closes[t] = [100.0] + [100.0 * (1 + i / 100.0)] * 13
    closes["SPY"] = [100.0] * 14
    panel = _panel(dates, closes, {t: "SPY" for t in tickers})
    frame = pd.DataFrame([{"run_date": dates[0], "ticker": t, "benchmark": "SPY",
                           "trend_component": float(i), "recovered": 0, "fundamentals_pit": 0}
                          for i, t in enumerate(tickers)])
    panel = panel._replace(frame=frame)
    cube = research.build_ic_cube(panel, ["trend_component"], max_h=1, min_names=3)
    assert cube.dates == [dates[0]]
    assert float(cube.ic[0, 0, 0]) == pytest.approx(1.0)   # perfectly monotone -> IC = +1


def test_ic_cube_skips_days_below_min_names():
    dates = [f"2025-01-{i:02d}" for i in range(1, 10)]
    closes = {t: [100.0, 101.0] + [101.0] * 7 for t in ["T0", "T1", "SPY"]}
    panel = _panel(dates, closes, {"T0": "SPY", "T1": "SPY"})
    frame = pd.DataFrame([{"run_date": dates[0], "ticker": t, "benchmark": "SPY",
                           "trend_component": 1.0, "recovered": 0, "fundamentals_pit": 0}
                          for t in ["T0", "T1"]])
    panel = panel._replace(frame=frame)
    cube = research.build_ic_cube(panel, ["trend_component"], max_h=1, min_names=30)
    assert cube.dates == []          # 2 names is not a cross-section


def test_summarize_decay_records_the_date_window_per_row():
    """Every decay row carries the snapshot-date span it was computed over. Long horizons rest on
    fewer, older, overlapping dates — h=250 can be one four-month market episode — so the window has
    to be visible on the row itself rather than inferred. (Also guards a real crash: numpy has no
    `minimum` ufunc for string dtypes, so these must be plain Python min/max.)"""
    dates = [f"2025-{m:02d}-{d:02d}" for m in (1, 2, 3) for d in (1, 2)]
    ic = np.full((len(dates), 1, 5), 0.2, np.float32)
    ic[3:, 0, 4] = np.nan                      # h=5 matures on only the first 3 dates
    cube = research.IcCube(ic=ic, n_obs=np.full((len(dates), 1, 5), 40, np.int32), dates=dates,
                           series=["trend_component"], horizons=[1, 2, 3, 4, 5])
    rows = research.summarize_decay(cube, "vX", "all_available")
    h1 = next(r for r in rows if r["horizon"] == 1)
    h5 = next(r for r in rows if r["horizon"] == 5)
    assert h1["n_days"] == 6 and h1["snapshot_date_max"] == "2025-03-02"
    assert h5["n_days"] == 3 and h5["snapshot_date_max"] == "2025-02-01"   # shorter, older window
    assert h5["sample_adequate"] is False                                  # and flagged as thin
    assert h1["ic_method"] == "mean_daily_cross_sectional_spearman"


def test_common_panel_ignores_an_all_null_series_instead_of_being_vetoed_by_it():
    """A series that is null EVERYWHERE (short_interest_component never backfills — it is live-only)
    must not veto the comparable panel. Requiring every series to be present made the intersection
    empty and produced NO common panel, silently removing the period control that the panel exists to
    provide: long horizons rest on older, shorter date windows, so an uncontrolled cross-horizon
    comparison can read a PERIOD effect as a HORIZON effect."""
    dates = [f"2025-01-{i:02d}" for i in range(1, 11)]
    ic = np.full((10, 3, 5), 0.2, np.float32)
    ic[:, 2, :] = np.nan                       # series 2 is null everywhere
    ic[7:, 0, 4] = np.nan                      # series 0 immature on the last 3 dates at h=5
    cube = research.IcCube(ic=ic, n_obs=np.full((10, 3, 5), 40, np.int32), dates=dates,
                           series=["a", "b", "short_interest_component"], horizons=[1, 2, 3, 4, 5])
    participating = [si for si in range(3) if not np.isnan(cube.ic[:, si, 4]).all()]
    assert participating == [0, 1]             # the all-null series is excluded, not decisive
    usable = ~np.isnan(cube.ic[:, participating, 4]).any(axis=1)
    assert usable.sum() == 7                   # a real panel survives instead of an empty one


# ---------------------------------------------------------------------------
# SUE (standardized unexpected earnings) and earnings timing
# ---------------------------------------------------------------------------

def _eps_q(period_end, filed, eps):
    return (period_end, filed, eps)


def test_sue_matches_the_same_SEASON_not_four_positions_back():
    """Filers skip quarters in XBRL (NVDA and KO both have gaps because some quarters are tagged
    year-to-date only). Stepping back four POSITIONS then compares against the wrong season, turning
    ordinary seasonality into a fake earnings surprise. Matching must key on period_end ~1 year back."""
    series = [
        _eps_q("2024-03-31", "2024-05-01", 1.0),
        _eps_q("2024-06-30", "2024-08-01", 2.0),
        # 2024-09-30 deliberately MISSING — the gap that breaks positional matching
        _eps_q("2024-12-31", "2025-02-01", 4.0),
        _eps_q("2025-03-31", "2025-05-01", 1.1),
    ]
    j = research._yoy_match(series, 3)
    assert j == 0 and series[j][0] == "2024-03-31"     # same season, not series[3-4]


def test_sue_is_stamped_at_the_filing_date_not_the_period_end():
    """A quarter ending 2025-03-31 is not public until early May. Keying SUE on period_end would hand
    the model five weeks of foresight and manufacture the very drift this is measuring."""
    series = [_eps_q(f"{y}-{m}", f, e) for y, m, f, e in [
        ("2023", "03-31", "2023-05-01", 1.0), ("2023", "06-30", "2023-08-01", 1.0),
        ("2023", "09-30", "2023-11-01", 1.0), ("2023", "12-31", "2024-02-01", 1.0),
        ("2024", "03-31", "2024-05-01", 1.2), ("2024", "06-30", "2024-08-01", 1.1),
        ("2024", "09-30", "2024-11-01", 1.3), ("2024", "12-31", "2025-02-01", 1.4),
        ("2025", "03-31", "2025-05-01", 3.0)]]
    out = research.sue_series(series, min_history=3, surprise_window=8)
    assert out, "no SUE produced"
    filed, period_end, sue, surprise, expected = out[-1]
    assert period_end == "2025-03-31"
    assert filed == "2025-05-01"          # the date it became usable, a month after the period ended
    assert surprise > 0 and sue > 0       # 3.0 against a ~1.2 expectation is a large positive surprise


def test_sue_requires_enough_history_to_standardize():
    # Too few prior surprises means the denominator is noise, so there is no SUE at all rather than
    # an arbitrary one (invariant #2).
    short = [_eps_q("2024-03-31", "2024-05-01", 1.0), _eps_q("2025-03-31", "2025-05-01", 2.0)]
    assert research.sue_series(short, min_history=6) == []


def test_sue_drift_term_stops_steady_growth_reading_as_a_surprise():
    """A company growing earnings at a constant rate should NOT post a positive surprise every
    quarter. The seasonal-random-walk-WITH-DRIFT expectation is what prevents that."""
    series, eps = [], 1.0
    for y in range(2020, 2026):
        for m, day in [("03", "31"), ("06", "30"), ("09", "30"), ("12", "31")]:
            series.append(_eps_q(f"{y}-{m}-{day}", f"{y}-{m}-{day}", eps))
            eps += 0.25                       # perfectly steady growth
    out = research.sue_series(series, min_history=3)
    assert out
    late = [r[2] for r in out[-4:]]
    # with drift modelled, a perfectly predictable ramp leaves essentially no surprise
    assert max(abs(s) for s in late) < 0.5, late


def test_expected_next_filing_is_a_forecast_from_past_cadence_not_the_actual_next_filing():
    """DAYS SINCE a filing is point-in-time; DAYS UNTIL the next one is not. Reading the next actual
    filing out of the table would let the model know an announcement date before it was announced.
    The pre-earnings window must therefore be forecast from the company's own PAST cadence."""
    filed = ["2024-05-01", "2024-08-01", "2024-11-01", "2025-02-01"]
    rows = [(f, f, 0.0, 0.0, 0.0) for f in filed]
    frame = pd.DataFrame([{"ticker": "T", "run_date": "2025-03-03"}])
    panel = research.Panel(frame=frame, closes={}, date_idx={}, benchmark_of={}, calendar=[])
    out = research.add_earnings_timing_columns(panel, {"T": (filed, rows)})
    r = out.frame.iloc[0]
    assert r["days_since_earnings_filing"] == 30          # 2025-02-01 -> 2025-03-03
    # cadence ~92 days, so the NEXT filing is expected in ~62 days. The real next filing date is
    # absent from the input entirely — which is the point.
    assert 55 <= r["expected_days_to_next_filing"] <= 70


def test_inverted_ic_is_reported_as_exact_negation_not_measured_twice():
    # Spearman IC of -x IS -IC(x). Presenting the inverted sign as an independent measurement would
    # dress one number up as two; the column is derived and labelled as such.
    dates = ["2025-01-01", "2025-01-02"]
    ic = np.array([[[0.3]], [[0.1]]], dtype=np.float32)
    cube = research.IcCube(ic=ic, n_obs=np.full((2, 1, 1), 40, np.int32), dates=dates,
                           series=["short_momentum_component"], horizons=[1])
    mean = float(np.nanmean(cube.ic[:, 0, 0]))
    assert mean == pytest.approx(0.2)
    assert -mean == pytest.approx(-0.2)


def test_baseline_weight_lookup_uses_the_real_SCORE_WEIGHTS_key():
    """SCORE_WEIGHTS is keyed "score_20d", not "20d". Looking it up wrongly returned an empty map,
    which apply_weights turned into an all-NaN column - so the hand-set baseline that the entire
    walk-forward comparison exists to beat was silently ABSENT rather than loudly broken, and every
    variant appeared to win by default."""
    from src.config import SCORE_WEIGHTS_BY_VERSION
    b = SCORE_WEIGHTS_BY_VERSION["v0.4_edgar_pit_fundamentals"]
    assert b.get("20d") in (None, {})                 # the wrong key really is empty
    assert b.get("score_20d"), "the right key must carry real weights"
    assert len(b["score_20d"]) >= 5


def test_apply_weights_with_an_empty_map_yields_all_nan():
    # The failure mode the new guard catches: no weights -> no scores, silently.
    frame = pd.DataFrame([{"trend_component": 80.0, "value_component": 40.0}])
    out = research.apply_weights(frame, {})
    assert out.isna().all()


# ---------------------------------------------------------------------------
# Panel column integrity — the mislabeling bug
# ---------------------------------------------------------------------------

def test_load_panel_column_list_is_deduplicated():
    """An extra_column that is ALSO a SERIES_COLUMN must appear once.

    The original builder tested membership against the base list only (the right-hand side of the
    `+=` is evaluated first), so short_momentum_component was requested twice. A duplicate label makes
    frame[series] return MORE columns than there are names, silently shifting every subsequent series
    by one position — the analysis then publishes real numbers under the wrong labels, which is worse
    than crashing because it looks like a finding."""
    base = ["run_date", "ticker", "benchmark", "recovered", "fundamentals_pit", "backfilled"]
    extra = ["return_5d", "short_momentum_component"]     # the second one overlaps SERIES_COLUMNS
    wanted, seen = [], set()
    for c in base + list(research.SERIES_COLUMNS) + list(extra):
        if c not in seen:
            seen.add(c)
            wanted.append(c)
    assert len(wanted) == len(set(wanted))
    assert wanted.count("short_momentum_component") == 1


def test_build_ic_cube_refuses_a_frame_with_duplicate_columns():
    """The cube's `series` list is the ONLY index-to-name mapping. A duplicate label shifts it, so
    the cube must refuse to build rather than emit mislabeled results."""
    dates = ["2025-01-01", "2025-01-02"]
    closes = {t: np.asarray([100.0, 101.0, 102.0]) for t in ["T0", "SPY"]}
    date_idx = {t: {d: i for i, d in enumerate(["2025-01-01", "2025-01-02", "2025-01-03"])}
                for t in closes}
    frame = pd.DataFrame([{"run_date": dates[0], "ticker": "T0", "benchmark": "SPY",
                           "trend_component": 1.0, "recovered": 0, "fundamentals_pit": 0}
                          for _ in range(40)])
    frame["ticker"] = [f"T{i}" for i in range(40)]
    for t in frame["ticker"]:
        closes[t] = np.asarray([100.0, 101.0, 102.0])
        date_idx[t] = {d: i for i, d in enumerate(["2025-01-01", "2025-01-02", "2025-01-03"])}
    dup = pd.concat([frame, frame[["trend_component"]]], axis=1)      # duplicate label
    panel = research.Panel(frame=dup, closes=closes, date_idx=date_idx,
                           benchmark_of={t: "SPY" for t in frame["ticker"]}, calendar=dates)
    with pytest.raises(AssertionError, match="duplicate columns"):
        research.build_ic_cube(panel, ["trend_component"], max_h=1, min_names=3)


def test_short_momentum_component_blends_three_inputs_not_one():
    """Spec: 40% return_5d + 35% return_10d + 25% return_20d percentiles, with negative-return
    penalties. Holding 5d fixed while moving ONLY the 10d and 20d inputs must move the score — if it
    does not, the component collapses to a transform of a single input."""
    from src import scoring
    from src.config import COMPONENT_PARAMS
    params = COMPONENT_PARAMS["short_momentum_component"]
    feats = {"return_5d": 0.02, "return_10d": 0.02, "return_20d": 0.02}
    low = scoring.short_momentum_component(
        feats, {"return_5d_percentile": 50, "return_10d_percentile": 10,
                "return_20d_percentile": 10}, params)
    high = scoring.short_momentum_component(
        feats, {"return_5d_percentile": 50, "return_10d_percentile": 90,
                "return_20d_percentile": 90}, params)
    assert high > low, "10d/20d inputs do not affect the score - it is a 5d transform"
    # and the blend is exactly the specified weights
    mid = scoring.short_momentum_component(
        feats, {"return_5d_percentile": 100, "return_10d_percentile": 0,
                "return_20d_percentile": 0}, params)
    assert mid == pytest.approx(40.0)      # 0.40 * 100, no penalties (all returns positive)


# ---------------------------------------------------------------------------
# Size-bucket decay comparison (v0.5)
# ---------------------------------------------------------------------------

def test_within_group_ic_is_exactly_invariant_to_a_shared_benchmark():
    """THE claim the whole large-vs-small comparison rests on.

    Large caps are benchmarked to sector ETFs and mid/small to broad size ETFs, because no liquid
    mid/small sector ETF family exists. Comparing buckets under different benchmark regimes would
    confound the result, so the comparison re-measures every bucket against ONE common benchmark.
    That is only legitimate if the choice of shared benchmark cannot change the answer.

    It cannot, and the reason is exact rather than statistical: a cross-sectional rank correlation
    computed WITHIN a group is unchanged by subtracting a per-date constant every member shares -
    subtracting the same number from every name cannot reorder them. Asserted directly here, because
    a plausible-sounding invariance claim that turns out to be only approximate would quietly
    invalidate the headline finding."""
    n = 40
    rng = np.random.default_rng(7)
    scores = rng.normal(size=n)
    raw_returns = rng.normal(size=n)

    def rank_ic(x, y):
        sx, sy = pd.Series(x), pd.Series(y)
        return float(sx.rank().corr(sy.rank(), method="pearson"))

    base = rank_ic(scores, raw_returns)
    for bench in (0.0, 0.013, -0.047, 12.5):          # any per-date constant
        assert rank_ic(scores, raw_returns - bench) == pytest.approx(base, abs=1e-12), bench


def test_size_buckets_load_from_the_watchlist_and_skip_blank_etf_rows(tmp_path):
    # ETF rows carry no bucket (they are benchmarks, not holdings) and must not be classified.
    import pandas as pd
    wl = tmp_path / "w.csv"
    pd.DataFrame([
        {"ticker": "AAA", "sector": "Industrials", "benchmark": "XLI", "size_bucket": "large"},
        {"ticker": "BBB", "sector": "Industrials", "benchmark": "IJR", "size_bucket": "small"},
        {"ticker": "SPY", "sector": "Index", "benchmark": "SPY", "size_bucket": ""},
    ]).to_csv(wl, index=False)
    out = research.load_size_buckets(str(wl))
    assert out == {"AAA": "large", "BBB": "small"}      # the ETF row is absent, not defaulted


def test_size_bucket_decay_skips_a_bucket_whose_benchmark_has_no_prices(tmp_path, capsys):
    """If a bucket's common benchmark is missing, the bucket is SKIPPED with a warning rather than
    quietly falling back to a different benchmark - a silent substitution would make two buckets
    incomparable while still printing a comparison."""
    import pandas as pd
    wl = tmp_path / "w.csv"
    pd.DataFrame([{"ticker": "AAA", "sector": "Industrials", "benchmark": "IJR",
                   "size_bucket": "small"}]).to_csv(wl, index=False)
    frame = pd.DataFrame([{"run_date": "2025-01-02", "ticker": "AAA", "benchmark": "IJR",
                           "recovered": 0, "fundamentals_pit": 0, "trend_component": 1.0}])
    panel = research.Panel(frame=frame, closes={}, date_idx={}, benchmark_of={"AAA": "IJR"},
                           calendar=["2025-01-02"])
    import unittest.mock as mock
    with mock.patch.object(research, "load_panel", return_value=panel):
        df = research.run_size_bucket_decay(db_path="unused", model_version="vX",
                                            output_dir=str(tmp_path), watchlist_path=str(wl))
    assert df.empty
    assert "no price history" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Regression-fitted weights (Job 3)
# ---------------------------------------------------------------------------

def test_nnls_recovers_a_known_non_negative_solution():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 4))
    y = X @ np.array([2.0, 0.0, 1.0, 0.0]) + rng.normal(scale=0.05, size=400)
    w = research.nnls_weights(X, y)
    assert w[0] == pytest.approx(2.0, abs=0.05)
    assert w[2] == pytest.approx(1.0, abs=0.05)
    assert w[1] == pytest.approx(0.0, abs=1e-6)


def test_nnls_clamps_a_genuinely_negative_relationship_to_zero_never_inverts_it():
    """Every component is defined "higher = better". A negative coefficient silently redefines what
    the component means, so the CONSTRAINT is the point - not a post-hoc clip. Here feature 1 truly
    has a -3 coefficient; the fit must land it at exactly zero and stay non-negative throughout."""
    rng = np.random.default_rng(1)
    X = rng.normal(size=(400, 4))
    y = X @ np.array([2.0, -3.0, 1.0, 0.0]) + rng.normal(scale=0.05, size=400)
    w = research.nnls_weights(X, y)
    assert (w >= 0).all(), "NNLS produced a negative weight"
    assert w[1] == pytest.approx(0.0, abs=1e-6)


def test_ridge_shrinks_toward_zero_as_alpha_grows():
    # The regularization must actually bind - an unpenalized fit on ~17 collinear components against
    # a few hundred effective observations is exactly how noise gets reported as signal.
    rng = np.random.default_rng(2)
    X = rng.normal(size=(200, 3))
    y = X @ np.array([3.0, 1.0, 0.0]) + rng.normal(scale=0.1, size=200)
    weak = research.ridge_weights(X, y, alpha=0.01)
    strong = research.ridge_weights(X, y, alpha=500.0)
    assert abs(strong[0]) < abs(weak[0])
    assert abs(weak[0]) == pytest.approx(3.0, abs=0.2)


def test_regression_fit_refuses_a_training_set_past_the_maturity_cutoff():
    """The same structural guard `fit_ic_weights` carries. The maturity cutoff is the entire
    difference between a trailing fit and a clairvoyant one, so BOTH fitting paths enforce it -
    a guard on only one path is a guard that will eventually be walked around."""
    cal = _calendar(50)
    w = research.TrainWindow(fit_seq=0, horizon=20, train_end_date=cal[40],
                             maturity_cutoff_date=cal[20],
                             train_dates=[cal[10], cal[30]],      # cal[30] is PAST the cutoff
                             oos_dates=[cal[41]])
    panel = research.Panel(frame=pd.DataFrame(), closes={}, date_idx={}, benchmark_of={},
                           calendar=cal)
    with pytest.raises(ValueError, match="lookahead"):
        research.fit_regression_weights(panel, w, "ridge", ["trend_component"])


def test_regression_fit_falls_back_to_equal_weights_not_to_the_baseline():
    """When a fit yields nothing usable it must fall back to EQUAL weights and say so. Falling back
    to SCORE_WEIGHTS would make the fitted variant silently reproduce the baseline and then appear
    to have matched it on its own merits - the comparison would be judging the baseline twice."""
    from src.config import SCORE_WEIGHTS
    cal = _calendar(50)
    w = research.TrainWindow(fit_seq=0, horizon=20, train_end_date=cal[40],
                             maturity_cutoff_date=cal[35], train_dates=[cal[10]],
                             oos_dates=[cal[41]])
    panel = research.Panel(frame=pd.DataFrame(columns=["run_date", "ticker"]), closes={},
                           date_idx={}, benchmark_of={}, calendar=cal)
    comps = ["trend_component", "risk_component"]
    weights, diag = research.fit_regression_weights(panel, w, "ridge", comps)
    assert diag["degenerate"] is True
    baseline = SCORE_WEIGHTS.get("score_20d", {})
    assert not all(weights.get(c) == baseline.get(c) for c in comps), "silently reused the baseline"


def test_an_all_null_component_does_not_veto_the_regression_fit():
    """short_interest_component is live-only (FINRA) and is null on EVERY backfilled row. The training
    matrix requires each listed component to be present on a row, so one all-null component drops
    100% of training rows and the fit silently yields nothing - which is what happened on v0.5:
    779,260 rows in, zero rows out, ridge and nnls producing no scores at all.

    This is the SAME rule the decay analysis already needed for its common panel. An all-null series
    cannot participate and must not veto; it gets weight zero and is FLAGGED, never imputed."""
    cal = _calendar(60)
    train_dates = cal[:30]
    rng = np.random.default_rng(3)
    rows = []
    for d in train_dates:
        for i in range(40):
            rows.append({"run_date": d, "ticker": f"T{i}", "benchmark": "SPY",
                         "trend_component": float(rng.normal()),
                         "risk_component": float(rng.normal()),
                         "short_interest_component": None})       # null on every single row
    frame = pd.DataFrame(rows)
    tickers = sorted(frame["ticker"].unique())
    closes = {t: np.linspace(100, 130, len(cal)) for t in tickers}
    closes["SPY"] = np.linspace(100, 110, len(cal))
    date_idx = {t: {d: i for i, d in enumerate(cal)} for t in closes}
    panel = research.Panel(frame=frame, closes=closes, date_idx=date_idx,
                           benchmark_of={t: "SPY" for t in tickers}, calendar=cal,
                           opens=closes, volumes={t: np.full(len(cal), 1e7) for t in closes})
    w = research.TrainWindow(fit_seq=0, horizon=5, train_end_date=cal[40],
                             maturity_cutoff_date=cal[35], train_dates=train_dates,
                             oos_dates=[cal[41]])
    comps = ["trend_component", "risk_component", "short_interest_component"]
    weights, diag = research.fit_regression_weights(panel, w, "ridge", comps,
                                                    alpha=1.0)
    assert diag["unavailable"] == ["short_interest_component"]
    assert weights["short_interest_component"] == 0.0
    # the two usable components must still have been fitted, not dropped along with it
    assert diag["n_train_rows"] > 0, "the all-null component vetoed the entire fit"
