"""Conditional-pattern harness — synthetic only, no DB, no network.

A harness that makes hypothesis testing cheap makes FALSE discovery cheap, so the tests here are
adversarial in the house idiom: each one names the wrong-but-plausible implementation it exists to
rule out. Two of them are load-bearing —

  * `test_no_condition_can_see_the_future` overwrites the future half of the price series and
    demands every mask come back bit-identical. A full-sample quantile ("top-decile week" measured
    against the whole two-year distribution) is the exact leak this catches, and it would produce a
    beautiful, false result rather than an error.
  * `test_family_null_calls_a_pure_noise_family_insignificant` runs the whole multiple-comparisons
    apparatus against data with no structure at all. If it hands back a "finding" there, every
    conclusion this module ever produces is worthless.
"""
import math

import numpy as np
import pytest

from src import patterns
from src.config import PARAMS


def _dates(n, start_weekday=0):
    """Real ISO dates on consecutive weekdays, so day-of-week logic is exercised honestly."""
    from datetime import date, timedelta
    out, d = [], date(2024, 1, 1) + timedelta(days=start_weekday)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _panel(closes, opens=None, dates=None):
    from datetime import date as _d
    closes = {t: np.asarray(v, dtype=np.float64) for t, v in closes.items()}
    n = len(next(iter(closes.values())))
    dates = dates or _dates(n)
    opens = {t: np.asarray(v, dtype=np.float64) for t, v in (opens or closes).items()}
    dow = np.asarray([_d.fromisoformat(x).weekday() for x in dates], dtype=np.int8)
    return patterns.PatternPanel(dates=dates, closes=closes, opens=opens, dow=dow)


# ---------------------------------------------------------------------------
# No-lookahead — the load-bearing property
# ---------------------------------------------------------------------------

def test_no_condition_can_see_the_future():
    """THE test.

    Every condition mask at index i must be a function of prices at index <= i and nothing else.
    The classic silent leak in seasonality work is a FULL-SAMPLE threshold: deciding what counted as
    a "strong week" in month 1 using the distribution of all 24 months. That produces a plausible
    backtest and no error, so it is asserted directly rather than reviewed.

    Method: build every condition on a series, then overwrite the entire second half of the price
    array with wildly different values and rebuild. Masks over the first half must be bit-identical.
    """
    rng = np.random.default_rng(7)
    n = 300
    base = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    half = n // 2

    mutated = base.copy()
    mutated[half:] = base[half:] * np.exp(np.cumsum(rng.normal(0.05, 0.20, n - half)))

    def build(series):
        p = _panel({"AAA": series, "BBB": base[::-1].copy()})
        return [
            patterns.cond_trailing_extreme(p, "AAA", 5, 0.10, min_history=40),
            patterns.cond_trailing_extreme(p, "AAA", 20, 0.10, upper=False, min_history=40),
            patterns.cond_streak(p, "AAA", 3, up=True),
            patterns.cond_above_sma(p, "AAA", 50),
            patterns.cond_rank_top_cross(p, "AAA", ["AAA", "BBB"], 5, k=1),
            patterns.cond_day_of_week(p, 4),
            patterns.cond_turn_of_month(p),
        ]

    for before, after in zip(build(base), build(mutated)):
        assert before.name == after.name
        assert np.array_equal(before.mask[:half], after.mask[:half]), (
            f"{before.name} changed in the PAST when only the FUTURE was rewritten — lookahead")


def test_expanding_quantile_never_uses_a_full_sample_threshold():
    """A rising series: under an expanding threshold, early values are extreme relative to the
    little history that exists, so the mask must fire well before the end. Under a full-sample
    threshold only the final 10% could ever fire — which is the bug's fingerprint."""
    values = np.arange(200, dtype=np.float64)
    mask = patterns._expanding_quantile_mask(values, 0.10, min_history=20, upper=True)
    # min_history=20 means the 20th observation (index 19) is the first eligible one.
    assert mask[19:].all(), "a monotonically rising series is always its own running maximum"
    assert not mask[:19].any(), "must not fire before min_history observations exist"


def test_forward_returns_are_nan_where_the_horizon_has_not_elapsed():
    """The guardrail. An unelapsed horizon must never be silently treated as a zero return, which
    would drag every conditional mean toward the baseline and hide real effects."""
    p = _panel({"AAA": [100.0] * 10})
    fwd = patterns.forward_returns(p, "AAA", 3)
    assert np.isnan(fwd[-3:]).all()
    assert not np.isnan(fwd[:-3]).any()


def test_tradable_return_fills_at_next_open_not_at_the_signal_close():
    """The condition is only KNOWN at date i's close, so a return measured from that same close is
    not reachable. Construction: a 2x gap between close(i) and open(i+1) makes the entry price
    unambiguous, mirroring the backtest's fill test."""
    closes = [100.0, 200.0, 220.0, 220.0]
    opens = [100.0, 200.0, 220.0, 220.0]
    p = _panel({"AAA": closes}, opens={"AAA": opens})
    optimistic = patterns.forward_returns(p, "AAA", 2, tradable=False)
    tradable = patterns.forward_returns(p, "AAA", 2, tradable=True)
    assert optimistic[0] == pytest.approx(220.0 / 100.0 - 1.0)   # close(0) -> close(2)
    assert tradable[0] == pytest.approx(220.0 / 200.0 - 1.0)     # open(1)  -> close(2)


# ---------------------------------------------------------------------------
# Effective sample size — the number that keeps a result honest
# ---------------------------------------------------------------------------

def test_weekly_triggers_are_not_penalised_like_daily_ones():
    """A Friday-only condition at h=5 fires once a week and its windows barely overlap, so all of
    its triggers are independent. The blanket `n_days / horizon` rule used elsewhere in this project
    would throw away ~80% of that sample and understate a real effect."""
    weekly = np.arange(0, 100, 5)
    assert patterns.effective_independent_n(weekly, 5) == len(weekly)


def test_consecutive_triggers_collapse_to_the_non_overlapping_count():
    """40 consecutive trigger days at h=20 share almost all of their forward window: ~2 independent
    observations, not 40. Reporting 40 would overstate the t-statistic by ~4.5x."""
    assert patterns.effective_independent_n(np.arange(40), 20) == 2
    assert patterns.effective_independent_n(np.array([]), 5) == 0


def test_min_detectable_effect_is_reported_so_a_null_is_readable():
    """"No effect found" and "no effect large enough to see with 554 sessions" are different claims.
    The MDE column is what separates them, so it must be present and correctly scaled."""
    rng = np.random.default_rng(3)
    series = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 250)))
    p = _panel({"AAA": series})
    cond = patterns.cond_day_of_week(p, 4)
    row = patterns.test_pattern(p, cond, "AAA", 1)
    assert row["min_detectable_effect_pct"] > 0
    fwd = patterns.forward_returns(p, "AAA", 1)
    trig = np.flatnonzero(cond.mask & ~np.isnan(fwd))
    std = np.std(fwd[trig], ddof=1)
    expected = 100.0 * PARAMS["pattern_power_z"] * std / math.sqrt(len(trig))
    assert row["min_detectable_effect_pct"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Effect measurement
# ---------------------------------------------------------------------------

def test_lift_is_measured_against_the_baseline_not_against_zero():
    """A pattern whose conditional return is +1% is worth nothing if the tape returns +1% on every
    day. Reporting the raw conditional mean as the finding is the most common way seasonality
    research fools itself; lift must net out the unconditional drift exactly."""
    p = _panel({"AAA": list(100 * 1.01 ** np.arange(60))})   # every single day is +1%
    cond = patterns.cond_day_of_week(p, 4)
    row = patterns.test_pattern(p, cond, "AAA", 1, min_triggers=1)
    assert row["mean_return_pct"] == pytest.approx(1.0)
    assert row["lift_pct"] == pytest.approx(0.0, abs=1e-9)


def test_a_planted_effect_is_recovered():
    """Sanity in the other direction: if Fridays really are weak, the harness must say so. A test
    suite that only proves the harness finds nothing would pass on a harness that does nothing."""
    n = 400
    dates = _dates(n)
    rng = np.random.default_rng(11)
    rets = rng.normal(0.0, 0.005, n)
    dow = np.asarray([__import__("datetime").date.fromisoformat(d).weekday() for d in dates])
    rets[dow == 4] -= 0.010                     # every Friday's NEXT-day return is dragged down
    closes = 100 * np.exp(np.cumsum(np.roll(rets, 1)))
    p = _panel({"AAA": closes}, dates=dates)
    row = patterns.test_pattern(p, patterns.cond_day_of_week(p, 4), "AAA", 1)
    assert row["lift_pct"] < 0
    assert row["t_stat"] < -2


def test_conjunction_is_the_intersection():
    p = _panel({"AAA": [100.0] * 40})
    fri = patterns.cond_day_of_week(p, 4)
    mon = patterns.cond_day_of_week(p, 0)
    assert not patterns.cond_and(fri, mon).mask.any()
    assert patterns.cond_and(fri, patterns.cond_not(mon)).mask.sum() == fri.mask.sum()


# ---------------------------------------------------------------------------
# Multiple comparisons — the reason this module is allowed to exist
# ---------------------------------------------------------------------------

def test_benjamini_hochberg_matches_a_hand_computed_case():
    p_values = [0.001, 0.008, 0.039, 0.041, 0.042, 0.060, 0.074, 0.205]
    # BH at q=0.05, m=8: largest rank k with p_k <= k/8*0.05 is k=4 (0.041 <= 0.025 is false;
    # 0.008 <= 0.0125 is true at k=2). Verified by hand below.
    assert patterns.benjamini_hochberg(p_values, 0.05) == [0, 1]
    assert patterns.benjamini_hochberg([], 0.05) == []
    assert patterns.benjamini_hochberg([None, float("nan")], 0.05) == []


def test_family_null_calls_a_pure_noise_family_insignificant():
    """THE other load-bearing test.

    Pure random returns, 40 calendar patterns, no structure whatsoever. Several rows WILL be
    nominally significant — that is the whole point, 40 tests at alpha=0.05 buys you ~2 by
    construction. The family-level null must not be fooled by them.

    If this ever fails, every finding this module produces is suspect."""
    rng = np.random.default_rng(2024)
    n = 500
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    p = _panel({"AAA": closes})

    specs = []
    for dow in range(5):
        for h in (1, 5, 10, 20):
            specs.append((patterns.cond_day_of_week(p, dow), "AAA", h, None))
    for m in range(1, 13):
        specs.append((patterns.cond_month(p, m), "AAA", 5, None))

    df = patterns.run_family(p, specs, "noise", n_perm=200)
    assert len(df) == len(specs)
    assert (df["family_size"] == len(specs)).all()
    assert df["family_null_p"].iloc[0] > 0.10, (
        "the family-level null found a 'pattern' in pure noise")
    assert not df["survives_bonferroni"].any()


def test_family_columns_make_the_uncorrected_p_impossible_to_quote_alone():
    """Every row must carry its correction beside it. A CSV that reports only `p_value` invites the
    reader to treat the best of 40 tests as if it were the only one."""
    rng = np.random.default_rng(5)
    p = _panel({"AAA": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))})
    specs = [(patterns.cond_day_of_week(p, d), "AAA", 1, None) for d in range(5)]
    df = patterns.run_family(p, specs, "dow", n_perm=50)
    for col in ("family_size", "bonferroni_threshold", "survives_bonferroni", "survives_bh_fdr",
                "expected_false_positives_at_alpha", "family_null_p", "oos_lift_pct",
                "sign_held_oos", "min_detectable_effect_pct", "effective_independent_n"):
        assert col in df.columns, f"missing correction column {col}"
    assert df["bonferroni_threshold"].iloc[0] == pytest.approx(PARAMS["pattern_alpha"] / 5)
    assert df["expected_false_positives_at_alpha"].iloc[0] == pytest.approx(5 * PARAMS["pattern_alpha"])


def test_permutation_null_is_reproducible():
    """A reported p-value that moves between runs is not a p-value. The seed lives in config."""
    rng = np.random.default_rng(9)
    p = _panel({"AAA": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 250)))})
    specs = [(patterns.cond_day_of_week(p, d), "AAA", 5, None) for d in range(5)]
    a = patterns.circular_shift_null(p, specs, n_perm=100)
    b = patterns.circular_shift_null(p, specs, n_perm=100)
    assert a[0] == b[0] and a[2] == b[2]


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------

def test_missing_bars_stay_nan_and_are_never_forward_filled():
    """A fabricated price produces a return of exactly 0% on a day that did not trade — real-looking
    data that biases every conditional mean toward 'nothing happened'. CLAUDE.md invariant #2."""
    p = _panel({"AAA": [100.0, np.nan, 102.0, 103.0]})
    fwd = patterns.forward_returns(p, "AAA", 1)
    assert np.isnan(fwd[0]) and np.isnan(fwd[1])
    assert fwd[2] == pytest.approx(103.0 / 102.0 - 1.0)


def test_a_two_observation_pattern_cannot_produce_a_finding():
    """Regression test for a REAL false positive this harness produced on its first live run.

    "SPY down 5 sessions in a row" fired exactly twice in 554 sessions, both times followed by a
    gain. Two points give a two-point standard deviation, which by luck was tiny, which gave
    t = 185, which handed the whole family a p = 0.010 "SIGNAL" verdict built on two coin flips.

    The row must still be REPORTED — suppressing it entirely would hide a real observation — but it
    must carry no t, no p, and no vote in the family correction."""
    n = 120
    closes = np.full(n, 100.0)
    closes[40], closes[41] = 99.0, 98.0     # two-day dip -> one trigger, then a lucky rally
    closes[42:] = 110.0
    closes[80], closes[81] = 109.0, 108.0   # a second, identical episode
    closes[82:] = 125.0
    p = _panel({"AAA": closes})
    cond = patterns.cond_streak(p, "AAA", 2, up=False)
    assert cond.mask.sum() == 2, "fixture must produce exactly two triggers"

    row = patterns.test_pattern(p, cond, "AAA", 5)
    assert row["n_triggers"] == 2
    assert row["mean_return_pct"] is not None, "the observation must still be described"
    assert row["t_stat"] is None and row["p_value"] is None, "no inference on 2 observations"
    assert row["below_inference_floor"] is True
    assert "independent observations" in row["note"]

    # And it must not be able to carry a family.
    specs = [(cond, "AAA", 5, None),
             (patterns.cond_day_of_week(p, 4), "AAA", 5, None)]
    df = patterns.run_family(p, specs, "floor", n_perm=25)
    assert len(df) == 2, "the untestable row stays in the OUTPUT"
    assert df["family_size"].iloc[0] == 1, "but not in the CORRECTION"
    assert df["family_untestable_rows"].iloc[0] == 1
    assert not df["survives_bonferroni"].any()


def test_p_values_use_the_t_distribution_not_the_normal_approximation():
    """At small df the normal understates the critical value — 2.36 vs 1.96 at 7 df — so a normal
    p-value would call a t of ~2.1 significant when it is not. Every sample in this project is
    small, which is exactly where the approximation fails."""
    t = 2.1
    t_p = patterns._t_sf(t, 7)
    normal_p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))
    assert t_p > normal_p, "the t tail must be FATTER than the normal at small df"
    assert normal_p < 0.05 < t_p, "this is the case where the two disagree about significance"
    # Sanity against published values: two-sided p at t=2.365, df=7 is 0.050.
    assert patterns._t_sf(2.365, 7) == pytest.approx(0.050, abs=0.001)
    assert patterns._t_sf(1.960, 10 ** 7) == pytest.approx(0.050, abs=0.001)


def test_a_series_measured_against_itself_is_named_not_silently_dropped():
    """Excess return of SPY vs SPY is identically zero: no variance, no t, no p. That row would
    otherwise land in the same "could not be tested" bucket as a genuinely thin sample, hiding a
    meaningless comparison behind an apparent data shortage. It must say which it is.

    Found on the first live run of this harness — five such rows were being reported."""
    rng = np.random.default_rng(4)
    p = _panel({"AAA": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))})
    row = patterns.test_pattern(p, patterns.cond_day_of_week(p, 4), "AAA", 1, benchmark="AAA")
    assert row["p_value"] is None
    assert "degenerate" in row["note"]
    assert row["below_inference_floor"] is False, "the sample is large; the COMPARISON is empty"
