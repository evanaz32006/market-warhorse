"""Conditional-pattern test harness — REPORT ONLY. Nothing here changes a score, a weight, or a
`model_version`.

The question this answers is "after condition X, does outcome Y happen?", turned from a day of
hand-coding into a query. That is the point AND the danger. Making a test cheap makes a FALSE
discovery cheap: run 200 seasonal patterns at alpha=0.05 and roughly 10 come back "significant"
having measured nothing at all. Seasonality is the most data-mined corner of finance, so this module
carries the correction machinery as a first-class output rather than as advice in a docstring:

  * per-test  — overlap-aware effective sample size, and the MINIMUM DETECTABLE EFFECT at 80% power,
                so "no signal" can be distinguished from "not enough data to see one";
  * family    — Bonferroni, Benjamini-Hochberg FDR, and a circular-shift null on the family's
                max |t| (White's Reality Check in spirit), which is the only one of the three that
                respects both the autocorrelation of daily returns and the correlation BETWEEN
                patterns tested on the same tape;
  * split     — every pattern is re-measured on a chronologically held-out tail.

No-lookahead is structural, not reviewed: a condition is a boolean mask built ONLY from prices at
index <= i (see `_expanding_quantile_mask`, which is the only non-obvious case), and
`tests/test_patterns.py` asserts it by overwriting the future half of the price array and requiring
every mask to come back bit-identical.

`patterns` imports `evaluation` and `storage`; NEVER the reverse. It is opt-in via
`app.py --research patterns` and cannot be reached from the nightly path.
"""

import math
import os
from collections import namedtuple
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from src import evaluation, storage
from src.config import PARAMS


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _output_dir(output_dir=None):
    path = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      *PARAMS["research_output_dir"].split("/"))
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Panel — one master calendar, every series aligned to it
# ---------------------------------------------------------------------------

# `closes` / `opens` are dict[ticker] -> float64 array of len(dates), NaN where that ticker had no
# bar on that session. Aligning everything to ONE calendar up front is what makes a condition on
# ticker A and an outcome on ticker B safe to index with the same integer.
PatternPanel = namedtuple("PatternPanel", "dates closes opens dow")


def load_pattern_panel(db_path=storage.DEFAULT_DB_PATH, tickers=None, calendar=None):
    """Align every requested ticker onto the master session calendar.

    Missing bars stay NaN. They are never forward-filled: a fabricated price would produce a return
    of exactly 0% on a day that did not trade, which reads as real data and biases both the condition
    and the outcome toward "nothing happened"."""
    dates = list(calendar or evaluation.trading_calendar(db_path=db_path))
    if not dates:
        return None
    pos = {d: i for i, d in enumerate(dates)}
    n = len(dates)
    closes, opens = {}, {}
    for t in sorted(set(tickers or [])):
        hist = storage.load_price_history(t, db_path=db_path)
        if not hist:
            continue
        c = np.full(n, np.nan)
        o = np.full(n, np.nan)
        for r in hist:
            i = pos.get(r["date"])
            if i is None:          # a session the calendar ticker did not trade — outside the panel
                continue
            c[i] = r["close"]
            o[i] = r["open"] if r["open"] is not None else r["close"]
        closes[t] = c
        opens[t] = o
    dow = np.asarray([date.fromisoformat(d).weekday() for d in dates], dtype=np.int8)
    return PatternPanel(dates=dates, closes=closes, opens=opens, dow=dow)


# ---------------------------------------------------------------------------
# Conditions — every mask[i] depends ONLY on data at index <= i
# ---------------------------------------------------------------------------

Condition = namedtuple("Condition", "name mask")


def _trailing_return(arr, lookback):
    """arr[i] / arr[i-lookback] - 1, NaN for i < lookback. Strictly backward-looking."""
    out = np.full(len(arr), np.nan)
    if lookback < len(arr):
        out[lookback:] = (arr[lookback:] / arr[:-lookback]) - 1.0
    return out


def _expanding_quantile_mask(values, q, min_history, upper=True):
    """True where values[i] sits in the top (or bottom) `q` of the history ENDING AT i.

    The one genuinely lookahead-prone primitive in this module. A full-sample quantile is the classic
    silent leak: "top decile week" computed against the whole 2-year distribution uses next year's
    prices to decide what counted as a strong week today. So the threshold at i is the quantile of
    values[:i+1] and nothing else, and it does not fire until `min_history` observations exist."""
    out = np.zeros(len(values), dtype=bool)
    seen = []
    for i, v in enumerate(values):
        if not np.isnan(v):
            seen.append(v)          # appended BEFORE the test, so i is included in its own history
        if len(seen) < min_history or np.isnan(v):
            continue
        thresh = np.quantile(seen, 1.0 - q if upper else q)
        out[i] = bool(v >= thresh) if upper else bool(v <= thresh)
    return out


def cond_day_of_week(panel, weekday, label=None):
    """Calendar-only, so trivially point-in-time. weekday: 0=Mon .. 4=Fri."""
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    return Condition(name=label or "dow=%s" % names[weekday], mask=(panel.dow == weekday))


def cond_turn_of_month(panel, last_k=3, first_k=3):
    """The last `last_k` sessions of a month plus the first `first_k` of the next.

    Uses only the CALENDAR — but note it must know a session is the month's last, which is knowable
    in advance from the exchange calendar, not from any future price. The panel's final month may be
    incomplete, so its end is excluded rather than guessed."""
    months = [d[:7] for d in panel.dates]
    mask = np.zeros(len(panel.dates), dtype=bool)
    idx_by_month = {}
    for i, m in enumerate(months):
        idx_by_month.setdefault(m, []).append(i)
    ordered = sorted(idx_by_month)
    for j, m in enumerate(ordered):
        idxs = idx_by_month[m]
        if j < len(ordered) - 1:
            for i in idxs[-last_k:]:
                mask[i] = True
        for i in idxs[:first_k]:
            mask[i] = True
    return Condition(name="turn_of_month(-%d,+%d)" % (last_k, first_k), mask=mask)


def cond_month(panel, month):
    mask = np.asarray([int(d[5:7]) == month for d in panel.dates], dtype=bool)
    return Condition(name="month=%02d" % month, mask=mask)


def cond_streak(panel, ticker, n, up=True):
    """`n` consecutive up (or down) closes ending AT i, inclusive."""
    c = panel.closes[ticker]
    chg = np.full(len(c), np.nan)
    chg[1:] = c[1:] - c[:-1]
    sign = (chg > 0) if up else (chg < 0)
    mask = np.zeros(len(c), dtype=bool)
    for i in range(n, len(c)):
        window = sign[i - n + 1:i + 1]
        mask[i] = bool(window.all()) and not bool(np.isnan(chg[i - n + 1:i + 1]).any())
    return Condition(name="%s:%s_streak>=%d" % (ticker, "up" if up else "down", n), mask=mask)


def cond_trailing_extreme(panel, ticker, lookback, q, upper=True, min_history=None):
    """Trailing `lookback`-session return in the top/bottom `q` of its OWN expanding history.

    This is the owner's "really good week" made testable: strong RELATIVE to what that series had
    actually done by then, not relative to a threshold picked with hindsight."""
    min_history = min_history if min_history is not None else PARAMS["pattern_min_history"]
    tr = _trailing_return(panel.closes[ticker], lookback)
    mask = _expanding_quantile_mask(tr, q, min_history, upper=upper)
    side = "top" if upper else "bot"
    return Condition(name="%s:%s%dpct_%dd_return" % (ticker, side, int(q * 100), lookback),
                     mask=mask)


def cond_above_sma(panel, ticker, window):
    """Close above its own trailing `window`-session mean, that mean ending at i."""
    c = panel.closes[ticker]
    mask = np.zeros(len(c), dtype=bool)
    for i in range(window - 1, len(c)):
        seg = c[i - window + 1:i + 1]
        if np.isnan(seg).any():
            continue
        mask[i] = bool(c[i] > seg.mean())
    return Condition(name="%s:above_sma%d" % (ticker, window), mask=mask)


def cond_rank_top_cross(panel, ticker, peers, lookback, k=1):
    """`ticker`'s trailing return is among the top `k` of its peer group on that date.

    Cross-sectional rather than time-series "strong" — closer to how a person actually says "tech had
    a really good week": good COMPARED TO the other sectors, not compared to its own past."""
    peers = [p for p in peers if p in panel.closes]
    trs = {p: _trailing_return(panel.closes[p], lookback) for p in peers}
    mask = np.zeros(len(panel.dates), dtype=bool)
    for i in range(len(panel.dates)):
        vals = [(trs[p][i], p) for p in peers if not np.isnan(trs[p][i])]
        if len(vals) < max(3, k + 1):
            continue
        vals.sort(reverse=True)
        mask[i] = ticker in [p for _, p in vals[:k]]
    return Condition(name="%s:top%d_of_peers_%dd" % (ticker, k, lookback), mask=mask)


def cond_and(*conditions, **kwargs):
    mask = conditions[0].mask.copy()
    for c in conditions[1:]:
        mask = mask & c.mask
    return Condition(name=kwargs.get("name") or " AND ".join(c.name for c in conditions), mask=mask)


def cond_not(condition):
    return Condition(name="NOT(%s)" % condition.name, mask=~condition.mask)


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

def forward_returns(panel, ticker, horizon, benchmark=None, tradable=False):
    """Vector of the outcome after each session i, NaN where D+h has not elapsed.

    `tradable=False` measures close(i) -> close(i+h): the research convention, and the one whose sign
    is comparable to every IC elsewhere in this project. It is also OPTIMISTIC — the condition is
    only known at i's close, so trading at i's close is not reachable.

    `tradable=True` measures open(i+1) -> close(i+h), which is. Both are reported for every pattern,
    so "the effect is real but you cannot get it" appears as a column rather than as a footnote
    somebody has to think of."""
    c = panel.closes[ticker]
    n = len(c)
    out = np.full(n, np.nan)
    entry = panel.opens[ticker] if tradable else c
    shift = 1 if tradable else 0
    for i in range(n):
        j = i + horizon
        e = i + shift
        if j >= n or e >= n or e > j:
            continue
        if np.isnan(entry[e]) or np.isnan(c[j]):
            continue
        out[i] = c[j] / entry[e] - 1.0
    if benchmark:
        out = out - forward_returns(panel, benchmark, horizon, benchmark=None, tradable=tradable)
    return out


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _betacf(a, b, x, max_iter=200, eps=1e-12):
    """Continued fraction for the incomplete beta function (modified Lentz). Standard numerical
    recipe, written out because this project has no scipy dependency and does not acquire one."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_sf(t, df):
    """Two-sided Student-t tail probability.

    NOT the normal approximation, deliberately. Every sample in this project is small — the whole
    reason `effective_independent_n` exists — and that is exactly where the normal understates the
    critical value: at 7 degrees of freedom the 5% two-sided cutoff is 2.36, not 1.96, so a normal
    p-value would call a t of 2.1 significant when it is not. Using the wrong reference distribution
    on small samples is the same class of error as ignoring the overlap in the first place."""
    if df <= 0:
        return None
    return float(_betai(0.5 * df, 0.5, df / (df + float(t) * float(t))))


def effective_independent_n(trigger_idx, horizon):
    """The number of NON-OVERLAPPING triggers, by greedy scan.

    Sharper than the blanket `n_days / horizon` used elsewhere in this project, and it has to be: a
    Friday-only condition at h=5 fires once a week, so its ~110 triggers barely overlap at all and
    the blanket rule would discard 80% of a real sample. Conversely a condition that fires on 40
    consecutive days at h=20 has ~2 independent observations, not 40. The greedy scan gets both
    right because it reads the ACTUAL trigger spacing instead of assuming daily firing."""
    if len(trigger_idx) == 0:
        return 0
    count, last = 0, -10 ** 9
    for i in trigger_idx:
        if i - last >= horizon:
            count += 1
            last = int(i)
    return count


def _t_and_p(sample, effective_n, min_effective_n=None):
    """(mean, t, p) — or (mean, None, None) when the sample is too small to support inference.

    Refusing to return a number is the point. A two-observation sample yields a two-point standard
    deviation, which can be arbitrarily small by luck and produces a t-statistic in the hundreds.
    That number is not "weak evidence", it is not evidence at all, and returning it lets it
    propagate into a family verdict."""
    floor = (min_effective_n if min_effective_n is not None
             else PARAMS["pattern_min_effective_n"])
    if len(sample) < 2 or effective_n < max(2, floor):
        return (float(np.mean(sample)) if len(sample) else None), None, None
    mean = float(np.mean(sample))
    std = float(np.std(sample, ddof=1))
    if std == 0:
        return mean, None, None
    t = mean / (std / math.sqrt(effective_n))
    return mean, float(t), _t_sf(t, effective_n - 1)


def _inference_note(eff_n, t, std):
    """Why a row carries no p-value. Never left blank — "untestable" has two very different causes
    and conflating them hides a degenerate comparison behind an apparent data shortage."""
    if eff_n < PARAMS["pattern_min_effective_n"]:
        return "only %d independent observations — described, not tested" % eff_n
    if t is None and (std == 0 or math.isnan(std)):
        return ("zero variance in the conditional sample — degenerate comparison "
                "(is the target being measured against itself?)")
    return ""


def test_pattern(panel, condition, target, horizon, benchmark=None, date_slice=None,
                 min_triggers=None):
    """One (condition, target, horizon) cell.

    Reports the CONDITIONAL mean against the UNCONDITIONAL mean over the same window. A pattern that
    "wins 58% of the time" is worthless if the tape wins 58% of the time anyway, so LIFT — not the
    raw conditional return — is the headline, and the t-statistic is computed on the
    conditional-minus-baseline difference over the non-overlapping trigger count."""
    min_triggers = min_triggers if min_triggers is not None else PARAMS["pattern_min_triggers"]
    fwd = forward_returns(panel, target, horizon, benchmark=benchmark)
    fwd_tradable = forward_returns(panel, target, horizon, benchmark=benchmark, tradable=True)
    valid = ~np.isnan(fwd)
    if date_slice is not None:
        window = np.zeros(len(valid), dtype=bool)
        window[date_slice] = True
        valid = valid & window
    trig = np.flatnonzero(condition.mask & valid)
    base_idx = np.flatnonzero(valid)
    eff_n = effective_independent_n(trig, horizon)

    row = {
        "condition": condition.name, "target": target, "horizon": horizon,
        "benchmark": benchmark or "", "n_triggers": int(len(trig)),
        "n_baseline_days": int(len(base_idx)),
        "trigger_rate_pct": (100.0 * len(trig) / len(base_idx)) if len(base_idx) else None,
        "effective_independent_n": int(eff_n),
    }
    if len(trig) == 0 or len(base_idx) == 0:
        row.update({"underpowered": True, "note": "no triggers in window"})
        return row

    baseline = float(np.mean(fwd[base_idx]))
    sample = fwd[trig]
    mean_diff, t, p = _t_and_p(sample - baseline, eff_n)
    std = float(np.std(sample, ddof=1)) if len(sample) > 1 else float("nan")
    trad = fwd_tradable[trig]
    row.update({
        "mean_return_pct": 100.0 * float(np.mean(sample)),
        "baseline_return_pct": 100.0 * baseline,
        "lift_pct": (100.0 * mean_diff) if mean_diff is not None else None,
        "hit_rate_pct": 100.0 * float(np.mean(sample > 0)),
        "baseline_hit_rate_pct": 100.0 * float(np.mean(fwd[base_idx] > 0)),
        "mean_tradable_pct": (100.0 * float(np.nanmean(trad))
                              if not bool(np.isnan(trad).all()) else None),
        "t_stat": t, "p_value": p,
        # Stated per row rather than left to the reader: an inference floor breach is why a row can
        # show a large lift and no p-value at all.
        "below_inference_floor": bool(eff_n < PARAMS["pattern_min_effective_n"]),
        # The column that turns a null result into a statement about POWER rather than about the
        # market. With 554 sessions these are often large, and "no effect found" beside an MDE of
        # 1.8% means only that an effect smaller than 1.8% was invisible from here.
        "min_detectable_effect_pct": (100.0 * PARAMS["pattern_power_z"] * std / math.sqrt(eff_n)
                                      if eff_n >= 2 and not math.isnan(std) else None),
        "underpowered": bool(len(trig) < min_triggers or eff_n < 2),
        "note": _inference_note(eff_n, t, std),
    })
    return row


# ---------------------------------------------------------------------------
# Family-level multiple-comparisons control
# ---------------------------------------------------------------------------

def benjamini_hochberg(p_values, q):
    """Indices surviving BH at false-discovery rate q. An empty list is a legitimate answer."""
    pairs = sorted((p, i) for i, p in enumerate(p_values)
                   if p is not None and not math.isnan(p))
    m = len(pairs)
    if m == 0:
        return []
    cutoff_rank = 0
    for rank, (p, _) in enumerate(pairs, start=1):
        if p <= (rank / float(m)) * q:
            cutoff_rank = rank
    return sorted(i for _, i in pairs[:cutoff_rank])


def circular_shift_null(panel, specs, n_perm=None, seed=None):
    """Empirical distribution of the family's MAX |t| when the conditions carry no information.

    Each replication rotates every condition mask by ONE SHARED offset and recomputes the whole
    family. Shared, not independent, deliberately: patterns tested on the same tape are correlated,
    and independent shifts would break that correlation and produce a null that is too WIDE — it
    would look conservative while actually being the wrong null.

    A rotation preserves each condition's trigger count and spacing exactly, so the effective sample
    size carries over unchanged; it destroys only the alignment between condition and outcome. That
    is the null hypothesis stated precisely.

    Returns (observed_max_abs_t, null array, family_p), where family_p is the fraction of
    replications whose best pattern beat the real family's best — i.e. the probability of a result
    this good appearing ANYWHERE in a family this size purely by chance."""
    n_perm = n_perm or PARAMS["pattern_permutations"]
    rng = np.random.default_rng(seed if seed is not None else PARAMS["pattern_perm_seed"])

    prepared = []
    for cond, target, horizon, benchmark in specs:
        fwd = forward_returns(panel, target, horizon, benchmark=benchmark)
        valid = ~np.isnan(fwd)
        base = float(np.mean(fwd[valid])) if valid.any() else None
        prepared.append((cond.mask, fwd, valid, horizon, base))

    def family_max(offset):
        best = 0.0
        for mask, fwd, valid, horizon, base in prepared:
            if base is None:
                continue
            m = np.roll(mask, offset) & valid
            trig = np.flatnonzero(m)
            eff_n = effective_independent_n(trig, horizon)
            _, t, _ = _t_and_p(fwd[trig] - base, eff_n)   # returns None below the inference floor
            if t is not None and abs(t) > best:
                best = abs(t)
        return best

    observed = family_max(0)
    n = len(panel.dates)
    null = np.empty(int(n_perm))
    for k in range(int(n_perm)):
        null[k] = family_max(int(rng.integers(1, n)))   # never 0 — that is the observed case
    # +1 top and bottom: under H0 the observed value is itself one draw from the null, so an
    # empirical p can never legitimately be exactly zero.
    family_p = float((np.sum(null >= observed) + 1) / (n_perm + 1))
    return observed, null, family_p


def run_family(panel, specs, family_name, q=None, alpha=None, n_perm=None, oos_split=None):
    """Test a family end to end and attach every correction to every row.

    The FAMILY is the unit of honesty here. A row's own p-value is not a finding; `survives_bonferroni`
    / `survives_bh_fdr` / the shared `family_null_p` are. They are written into the CSV alongside the
    raw p precisely so a reader cannot accidentally quote the uncorrected number."""
    alpha = alpha if alpha is not None else PARAMS["pattern_alpha"]
    q = q if q is not None else PARAMS["pattern_fdr_q"]
    split = oos_split if oos_split is not None else PARAMS["pattern_oos_split"]
    n = len(panel.dates)
    cut = int(n * split)

    rows = []
    for cond, target, horizon, benchmark in specs:
        row = test_pattern(panel, cond, target, horizon, benchmark=benchmark)
        # Chronological split, always reported. A pattern that reverses sign out of sample is the
        # signature of a data-mined result, and that is more informative than any p-value.
        ins = test_pattern(panel, cond, target, horizon, benchmark=benchmark,
                           date_slice=slice(0, cut))
        oos = test_pattern(panel, cond, target, horizon, benchmark=benchmark,
                           date_slice=slice(cut, n))
        row["in_sample_lift_pct"] = ins.get("lift_pct")
        row["oos_lift_pct"] = oos.get("lift_pct")
        row["oos_n_triggers"] = oos.get("n_triggers")
        row["sign_held_oos"] = (
            None if row.get("lift_pct") is None or oos.get("lift_pct") is None
            else bool(np.sign(row["lift_pct"]) == np.sign(oos["lift_pct"])))
        rows.append(row)

    # A row that could not be tested must not COUNT as a test. Two separate reasons:
    #   * Bonferroni divides by the family size, so padding the family with untestable rows would
    #     make the correction look stricter than the number of real tests warrants;
    #   * the family's max |t| is the headline verdict, and letting a two-observation row supply it
    #     is precisely how "SPY down 5 days in a row" (n=2, t=185) produced a false SIGNAL on the
    #     first real run of this harness.
    # Untested rows stay in the CSV with their descriptive statistics and an explicit note — they
    # are omitted from the CORRECTION, never from the OUTPUT.
    testable = [i for i, r in enumerate(rows) if r.get("p_value") is not None]
    m = len(testable)
    p_values = [rows[i].get("p_value") for i in testable]
    bonf = alpha / m if m else alpha
    survivors = {testable[k] for k in benjamini_hochberg(p_values, q)}
    tested_specs = [specs[i] for i in testable]
    if tested_specs:
        observed, null, family_p = circular_shift_null(panel, tested_specs, n_perm=n_perm)
        null_p95 = float(np.percentile(null, 95))
    else:
        observed, family_p, null_p95 = None, None, None

    for i, r in enumerate(rows):
        p = r.get("p_value")
        r.update({
            "family": family_name,
            "family_size": m,
            "family_untestable_rows": len(rows) - m,
            "alpha": alpha,
            "bonferroni_threshold": bonf,
            "survives_bonferroni": bool(p is not None and p <= bonf),
            "survives_bh_fdr": bool(i in survivors),
            "expected_false_positives_at_alpha": round(m * alpha, 2),
            "n_nominally_significant": sum(1 for pv in p_values if pv is not None and pv <= alpha),
            "family_max_abs_t": observed,
            "family_null_p": family_p,
            "family_null_max_abs_t_p95": null_p95,
            "generated_at": _now_iso(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Families — the hypotheses themselves
# ---------------------------------------------------------------------------
#
# A "family" is one pre-declared block of related tests, corrected together. The grouping is not
# cosmetic: correcting for multiplicity only means anything if the family is fixed BEFORE the
# results are seen. Adding a pattern after looking, or moving a winner into a smaller family, is the
# exact manoeuvre these corrections exist to prevent — so families are defined here, in code, as
# whole blocks, and every member is reported whether it is interesting or not.

def pattern_universe():
    """Every ETF the harness ranks over: the 11 GICS sector SPDRs plus QQQ/SMH plus the size
    benchmarks. Read from config rather than listed here, per CLAUDE.md invariant #3."""
    from src.config import SECTOR_BENCHMARK_MAP, SIZE_BUCKET_BENCHMARK
    return sorted(set(SECTOR_BENCHMARK_MAP.values())
                  | set(SIZE_BUCKET_BENCHMARK.values())
                  | {"SMH", "SPY"})


def family_day_of_week(panel, index_ticker="SPY"):
    """The owner's "historically weaker Fridays", at index level, unconditional."""
    return [(cond_day_of_week(panel, d), index_ticker, h, None)
            for d in range(5) for h in (1, 5)]


def family_sector_day_of_week(panel, sectors, index_ticker="SPY"):
    """Same question one level down: does any SECTOR have a weekday tilt against the index?

    Measured as EXCESS vs SPY, which is the only version that could ever be acted on — a sector-wide
    Friday effect that is really just a market-wide Friday effect is not a sector pattern."""
    # The index itself is excluded: its excess return against itself is identically zero, which
    # produces a zero-variance sample, no t-statistic, and a row that would quietly land in the
    # "could not be tested" bucket as though the data were thin rather than the comparison
    # meaningless. Caught on the first live run — five such rows were being reported.
    return [(cond_day_of_week(panel, d), s, 1, index_ticker)
            for s in sectors if s != index_ticker for d in range(5)]


def family_calendar_seasonality(panel, index_ticker="SPY"):
    """Turn-of-month and month-of-year.

    Included with a warning attached rather than omitted: 554 sessions is TWO observations per
    calendar month, so every month-of-year row here is underpowered by construction. It is reported
    so the underpowered flag and the MDE column say so explicitly, instead of the question being
    quietly skipped and then re-asked later by someone who assumes it was never tested."""
    specs = [(cond_turn_of_month(panel, last_k=k, first_k=k), index_ticker, h, None)
             for k in (1, 3) for h in (1, 5)]
    specs += [(cond_month(panel, m), index_ticker, 5, None) for m in range(1, 13)]
    return specs


def family_streaks(panel, index_ticker="SPY"):
    """"After N consecutive up days, what happens?" — short-horizon reversal / continuation."""
    specs = []
    for n in (2, 3, 4, 5):
        for h in (1, 5, 10):
            specs.append((cond_streak(panel, index_ticker, n, up=True), index_ticker, h, None))
            specs.append((cond_streak(panel, index_ticker, n, up=False), index_ticker, h, None))
    return specs


def family_strong_week_reversal(panel, sectors, index_ticker="SPY"):
    """THE owner's hypothesis, in all three readings of "a really good week in the tech sector".

    The phrasing is ambiguous and the readings are not equivalent, so all three are tested rather
    than one being chosen silently:
      1. strong vs ITS OWN past   — trailing 5-day return in the top decile of its expanding history;
      2. strong vs ITS PEERS      — the best-performing sector of the week, cross-sectionally;
      3. strong AND it is Thursday — so the measured outcome lands specifically on the Friday.
    Every outcome is EXCESS vs the index: the claim is that the SECTOR gives back, not that the whole
    market does."""
    specs = []
    thursday = cond_day_of_week(panel, 3)
    for s in sectors:
        if s == index_ticker:
            continue
        own = cond_trailing_extreme(panel, s, 5, 0.10, upper=True)
        peer = cond_rank_top_cross(panel, s, sectors, 5, k=1)
        for h in (1, 5):
            specs.append((own, s, h, index_ticker))
            specs.append((peer, s, h, index_ticker))
        specs.append((cond_and(own, thursday, name="%s AND next-session-is-Friday" % own.name),
                      s, 1, index_ticker))
    return specs


def family_regime(panel, index_ticker="SPY"):
    """Trend state of the index — the cheap version of the breadth/regime work still on the list."""
    specs = []
    for w in (50, 200):
        above = cond_above_sma(panel, index_ticker, w)
        for h in (5, 20):
            specs.append((above, index_ticker, h, None))
            specs.append((cond_not(above), index_ticker, h, None))
    return specs


FAMILY_BUILDERS = {
    "day_of_week": lambda p, s: family_day_of_week(p),
    "sector_day_of_week": lambda p, s: family_sector_day_of_week(p, s),
    "calendar_seasonality": lambda p, s: family_calendar_seasonality(p),
    "streaks": lambda p, s: family_streaks(p),
    "strong_week_reversal": lambda p, s: family_strong_week_reversal(p, s),
    "regime": lambda p, s: family_regime(p),
}


def run_pattern_research(db_path=storage.DEFAULT_DB_PATH, output_dir=None, families=None,
                         n_perm=None):
    """Run every family and write one CSV per family plus a combined file. REPORT ONLY.

    Prints a headline block that leads with the FAMILY-level verdict, never with the best row's raw
    p-value. That ordering is deliberate: the single most likely way this harness gets misused is
    someone sorting the combined CSV by p_value and quoting the top line."""
    tickers = pattern_universe()
    panel = load_pattern_panel(db_path=db_path, tickers=tickers)
    if panel is None:
        print("[patterns] no trading calendar — nothing to test")
        return pd.DataFrame()
    available = [t for t in tickers if t in panel.closes]
    missing = sorted(set(tickers) - set(available))
    if missing:
        print("[patterns] no price history for %s — excluded (never substituted)"
              % ", ".join(missing))

    names = list(families or FAMILY_BUILDERS)
    out_dir = _output_dir(output_dir)
    all_rows = []
    print("[patterns] %d sessions (%s .. %s), %d series"
          % (len(panel.dates), panel.dates[0], panel.dates[-1], len(available)))

    for name in names:
        builder = FAMILY_BUILDERS[name]
        specs = [s for s in builder(panel, available) if s[1] in panel.closes]
        if not specs:
            print("[patterns] %-22s no testable specs — skipped" % name)
            continue
        df = run_family(panel, specs, name, n_perm=n_perm)
        path = os.path.join(out_dir, "patterns_%s.csv" % name)
        df.to_csv(path, index=False)
        all_rows.append(df)

        fam_p = df["family_null_p"].iloc[0]
        m = int(df["family_size"].iloc[0])
        untested = int(df["family_untestable_rows"].iloc[0])
        n_sig = int(df["n_nominally_significant"].iloc[0])
        exp_fp = float(df["expected_false_positives_at_alpha"].iloc[0])
        if fam_p is None or pd.isna(fam_p):
            print("[patterns] %-22s no row met the inference floor — nothing tested" % name)
            continue
        verdict = "SIGNAL" if fam_p <= 0.05 else "nothing beyond chance"
        print("[patterns] %-22s m=%-3d family_p=%.3f  %-22s  nominally sig %d (expect %.1f by "
              "chance)%s  -> %s"
              % (name, m, fam_p, verdict, n_sig, exp_fp,
                 ("  [%d row(s) below the inference floor, described only]" % untested)
                 if untested else "", os.path.basename(path)))

    if not all_rows:
        return pd.DataFrame()
    combined = pd.concat(all_rows, ignore_index=True)
    combined_path = os.path.join(out_dir, "patterns_all.csv")
    combined.to_csv(combined_path, index=False)
    print("[patterns] %d tests across %d families -> %s"
          % (len(combined), len(all_rows), combined_path))
    return combined
