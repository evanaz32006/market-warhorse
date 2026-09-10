"""Research analyses — REPORT ONLY. Nothing here changes a score, a weight, or a model_version.

Deliberately separate from `evaluation.py`, which runs on the daily critical path (`app.main` calls it
every night). These analyses take tens of seconds to minutes and are opt-in via `app.py --research`,
so it is structurally impossible for the nightly job to invoke one by accident.

`research` imports `evaluation`; NEVER the reverse. The no-lookahead primitives (`trading_calendar`,
`maturity_date`, `_spearman_ic`, `has_stale_fundamentals`) live in exactly one place and are borrowed
from here, so a second, subtly-different definition can't drift into existence.

Three analyses:
  (a) `run_decay_analysis`      — IC at EVERY horizon 1..N, to find where signal actually peaks.
  (b) `run_walk_forward_analysis` — IC-weighted composite scored strictly out-of-sample.
  (c) `run_quality_decomposition` — IC per leg of the quality composite, to tell a regime effect
                                    (all legs negative together) from a structural defect (one leg).
"""

import math
import os
from bisect import bisect_right
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src import evaluation, storage
from src.config import (FUNDAMENTAL_PERCENTILE_GROUPS, PARAMS, SCORE_WEIGHTS,
                        SCORE_WEIGHTS_BY_VERSION, SITOUT_COMPONENTS, SIZE_BUCKET_BENCHMARK)

# Every series a decay curve is computed for: the 16 components plus the 4 composites.
SERIES_COLUMNS = ([c for c in storage.SCORE_COLUMNS if not c.startswith("score_")]
                  + ["score_5d", "score_20d", "score_60d", "score_120d"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _output_dir(output_dir=None):
    path = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                      *PARAMS["research_output_dir"].split("/"))
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Shared panel machinery (used by every analysis below)
# ---------------------------------------------------------------------------

# `opens` and `volumes` are TRAILING fields with defaults so every existing constructor call
# (and every test helper that builds a Panel by hand) keeps working unchanged.
Panel = namedtuple("Panel", "frame closes date_idx benchmark_of calendar opens volumes",
                   defaults=({}, {}))


def load_panel(db_path, model_version, extra_columns=()):
    """Load the snapshot panel plus each ticker's price series, ONCE.

    `storage.load_all_snapshots` returns every one of the 135 columns as Python dicts; at 278k rows
    that is the memory bottleneck. Here only the columns an analysis actually reads are pulled, and
    prices become float64 numpy arrays so forward returns can be computed as a single vectorized
    slice rather than a Python loop per horizon."""
    # De-duplicated deliberately. The earlier form evaluated `c not in wanted` against the BASE
    # list only (the right-hand side is built before the +=), so any extra_column that was also a
    # SERIES_COLUMN got listed twice. A duplicate label makes frame[series] return MORE columns
    # than names, which silently shifts every series after it by one position — the analysis then
    # reports real numbers under the wrong labels, which is worse than crashing.
    base = ["run_date", "ticker", "benchmark", "recovered", "fundamentals_pit", "backfilled"]
    wanted, seen = [], set()
    for c in base + list(SERIES_COLUMNS) + list(extra_columns):
        if c not in seen:
            seen.add(c)
            wanted.append(c)
    rows = storage.load_all_snapshots(db_path, model_version=model_version)
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    keep = [c for c in wanted if c in frame.columns]
    assert len(keep) == len(set(keep)), f"duplicate columns requested: "\
        f"{[c for c in keep if keep.count(c) > 1]}"
    frame = frame[keep].copy()

    closes, date_idx, opens, volumes = {}, {}, {}, {}
    for t in sorted(set(frame["ticker"]) | set(frame["benchmark"])):
        hist = storage.load_price_history(t, db_path=db_path)
        if not hist:
            continue
        closes[t] = np.asarray([r["close"] for r in hist], dtype=np.float64)
        # OHLCV is fully populated in price_history but only `close` was ever extracted. A
        # portfolio backtest needs the OPEN (you cannot fill at the close you needed in order to
        # compute the decision) and the VOLUME (dollar liquidity drives spread and impact).
        opens[t] = np.asarray([(r["open"] if r["open"] is not None else r["close"])
                               for r in hist], dtype=np.float64)
        volumes[t] = np.asarray([(r["volume"] or 0.0) for r in hist], dtype=np.float64)
        date_idx[t] = {r["date"]: i for i, r in enumerate(hist)}

    benchmark_of = dict(zip(frame["ticker"], frame["benchmark"]))
    return Panel(frame=frame, closes=closes, date_idx=date_idx, benchmark_of=benchmark_of,
                 calendar=evaluation.trading_calendar(db_path=db_path),
                 opens=opens, volumes=volumes)


def forward_excess_vector(ticker, benchmark, snapshot_date, panel, max_h):
    """np.float32[max_h] of (ticker forward return - benchmark forward return) for h = 1..max_h.

    The vectorized twin of `evaluation._forward_return`, carrying the identical guardrail: an entry
    is NaN wherever D+h has not elapsed for EITHER series, so an unelapsed horizon can never be
    silently treated as a zero return. Computed as one numpy slice-and-divide per leg instead of
    max_h separate Python calls — this is what makes 250 horizons feasible at all."""
    out = np.full(max_h, np.nan, dtype=np.float32)
    ti, bi = panel.date_idx.get(ticker), panel.date_idx.get(benchmark)
    if ti is None or bi is None:
        return out
    i, j = ti.get(snapshot_date), bi.get(snapshot_date)
    if i is None or j is None:
        return out
    tc, bc = panel.closes[ticker], panel.closes[benchmark]
    if not tc[i] or not bc[j]:
        return out
    # `idx + h >= len` is the guardrail; as a slice that is simply "however many bars actually exist"
    n = min(max_h, len(tc) - i - 1, len(bc) - j - 1)
    if n <= 0:
        return out
    out[:n] = ((tc[i + 1:i + 1 + n] / tc[i]) - (bc[j + 1:j + 1 + n] / bc[j])).astype(np.float32)
    return out


def _rank_columns(mat):
    """Column-wise ranks of a 2-D array, NaNs left as NaN. Ranks are what a Spearman IC needs, and
    double-argsort is far cheaper than a pandas rank per column when there are 250 columns."""
    out = np.full(mat.shape, np.nan, dtype=np.float64)
    for c in range(mat.shape[1]):
        col = mat[:, c]
        ok = ~np.isnan(col)
        k = int(ok.sum())
        if k < 3:
            continue
        vals = col[ok]
        order = np.argsort(np.argsort(vals, kind="stable"), kind="stable").astype(np.float64)
        out[ok, c] = order
    return out


def _pairwise_spearman(score_ranks, excess_ranks):
    """(n_series, n_horizons) matrix of rank correlations, computed pairwise-complete.

    Spearman = Pearson of the ranks, which is why this project needs no scipy (mirrors
    `evaluation._spearman_ic`). Done as an explicit loop over series x horizons rather than one
    matmul: a matmul would need a shared missingness mask, and the honest thing is to let each
    (series, horizon) pair use exactly the names present for BOTH."""
    ns, nh = score_ranks.shape[1], excess_ranks.shape[1]
    ic = np.full((ns, nh), np.nan, dtype=np.float32)
    n_obs = np.zeros((ns, nh), dtype=np.int32)
    for s in range(ns):
        sc = score_ranks[:, s]
        s_ok = ~np.isnan(sc)
        if s_ok.sum() < 3:
            continue
        for h in range(nh):
            ex = excess_ranks[:, h]
            both = s_ok & ~np.isnan(ex)
            k = int(both.sum())
            n_obs[s, h] = k
            if k < 3:
                continue
            a, b = sc[both], ex[both]
            a = a - a.mean()
            b = b - b.mean()
            denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
            if denom > 0:
                ic[s, h] = float((a * b).sum()) / denom
    return ic, n_obs


IcCube = namedtuple("IcCube", "ic n_obs dates series horizons")


def build_ic_cube(panel, series_columns, max_h, min_names=None, date_stride=1,
                  pit_filter=True):
    """The core of both (a) and (b): daily cross-sectional Spearman IC for every (series, horizon).

    Streams by run_date and never materializes a 250-column-per-row table — the dict-per-row design
    in `evaluation.evaluate_all_snapshots` was measured at ~13 minutes and ~23 GB when extended to
    250 horizons, which is why this path exists separately.

    Returns ic[n_dates, n_series, n_horizons] as float32 plus the matching observation counts, so
    every downstream number (a decay curve, a trailing training window) is a slice of one object
    that was built once."""
    min_names = min_names or PARAMS["decay_min_names_per_day"]
    frame = panel.frame
    if pit_filter:
        frame = frame[~frame.apply(evaluation.has_stale_fundamentals, axis=1)]
    series = [c for c in series_columns if c in frame.columns]
    # The cube's `series` list is the ONLY thing mapping a column index back to a name. If the
    # frame carries a duplicate label, frame[series] widens and every later series is reported
    # under the wrong name. Refuse rather than mislabel.
    dupes = [c for c in series if list(frame.columns).count(c) > 1]
    assert not dupes, f"frame has duplicate columns {dupes}; series-to-column mapping would shift"

    all_dates = sorted(frame["run_date"].dropna().unique())
    dates = all_dates[::date_stride] if date_stride > 1 else all_dates

    ic_by_date, n_by_date, kept_dates = [], [], []
    for d in dates:
        sub = frame[frame["run_date"] == d]
        if len(sub) < min_names:
            continue
        excess = np.vstack([forward_excess_vector(t, panel.benchmark_of.get(t, "SPY"), d, panel, max_h)
                            for t in sub["ticker"]]).astype(np.float64)
        scores = sub[series].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float64)
        ic, n_obs = _pairwise_spearman(_rank_columns(scores), _rank_columns(excess))
        ic_by_date.append(ic)
        n_by_date.append(n_obs)
        kept_dates.append(d)

    if not kept_dates:
        return IcCube(ic=np.zeros((0, len(series), max_h), np.float32),
                      n_obs=np.zeros((0, len(series), max_h), np.int32),
                      dates=[], series=series, horizons=list(range(1, max_h + 1)))
    return IcCube(ic=np.stack(ic_by_date), n_obs=np.stack(n_by_date), dates=kept_dates,
                  series=series, horizons=list(range(1, max_h + 1)))


# ---------------------------------------------------------------------------
# (a) Signal decay curve
# ---------------------------------------------------------------------------

def summarize_decay(cube, model_version, sample_mode, date_subset=None):
    """Collapse the cube into one row per (series, horizon): mean/median/std of the DAILY ICs.

    Mean-of-daily-cross-sectional-IC, NOT the pooled IC `build_performance_review` reports. Each day
    gets equal weight, no cross-date contamination, and it yields IC_std for free (which the
    walk-forward `ic_ratio` variant needs). The two WILL differ visibly, so every row carries
    `ic_method` to say which one it is."""
    rows = []
    mask = (np.isin(np.array(cube.dates), list(date_subset))
            if date_subset is not None else np.ones(len(cube.dates), bool))
    if not mask.any():
        return rows
    dates = np.array(cube.dates)[mask]
    for si, s in enumerate(cube.series):
        kind = "composite" if s.startswith("score_") else "component"
        for hi, h in enumerate(cube.horizons):
            col = cube.ic[mask, si, hi]
            good = ~np.isnan(col)
            n_days = int(good.sum())
            vals = col[good].astype(np.float64)
            std = float(vals.std(ddof=1)) if n_days > 1 else None
            mean = float(vals.mean()) if n_days else None
            rows.append({
                "model_version": model_version, "series": s, "series_kind": kind, "horizon": h,
                "sample_mode": sample_mode,
                "mean_ic": mean, "median_ic": float(np.median(vals)) if n_days else None,
                "std_ic": std,
                "ic_t_stat_overlap_adj": evaluation._overlap_adjusted_t(mean, std, n_days, h),
                "pct_days_ic_positive": float((vals > 0).mean() * 100.0) if n_days else None,
                "n_days": n_days,
                "n_names_avg": float(cube.n_obs[mask, si, hi][good].mean()) if n_days else 0.0,
                # plain min/max over a Python list: numpy has no `minimum` ufunc for string dtypes,
                # and these dates exist precisely so a shrinking, drifting window stays visible
                "snapshot_date_min": min(dates[good].tolist()) if n_days else None,
                "snapshot_date_max": max(dates[good].tolist()) if n_days else None,
                # A horizon can be "computed" off a handful of overlapping windows from one market
                # episode. This flag is what stops that being read as a decay curve.
                "sample_adequate": bool(n_days >= PARAMS["decay_min_days"]),
                "ic_method": "mean_daily_cross_sectional_spearman",
                "date_stride": PARAMS["decay_date_stride"],
                "min_names_per_day": PARAMS["decay_min_names_per_day"],
                "generated_at": _now_iso(),
            })
    return rows


def run_decay_analysis(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                       max_h=None):
    """IC at every horizon 1..max_h for every component and composite -> signal_decay.csv.

    The 5/20/60/120 horizons were chosen by guess. This measures where IC actually peaks, i.e. the
    natural holding period the data supports rather than the one we assumed."""
    model_version = model_version or PARAMS["model_version"]
    max_h = max_h or PARAMS["decay_max_horizon"]
    panel = load_panel(db_path, model_version)
    if panel is None:
        print(f"[research] no snapshots for {model_version}")
        return pd.DataFrame()

    cube = build_ic_cube(panel, SERIES_COLUMNS, max_h,
                         date_stride=PARAMS["decay_date_stride"])
    rows = summarize_decay(cube, model_version, "all_available")

    # A strictly comparable view: the dates where EVERY series has a matured observation, capped at
    # a horizon that leaves a usable panel. Components and composites do not start on the same date
    # (composites need 200+ sessions of history), so laying their raw curves on one chart is
    # apples-to-oranges without this.
    cap = min(PARAMS["decay_common_panel_max_horizon"], max_h)
    if cube.dates:
        cap_i = cube.horizons.index(cap)
        # A series that is null EVERYWHERE (short_interest_component never backfills — it is
        # live-only from FINRA/yfinance) cannot participate in a common panel and must not veto it.
        # Requiring every series to be present made the intersection empty and silently produced no
        # comparable panel at all, which is worse than useless: it removes the control without saying so.
        participating = [si for si in range(len(cube.series))
                         if not np.isnan(cube.ic[:, si, cap_i]).all()]
        usable = ~np.isnan(cube.ic[:, participating, cap_i]).any(axis=1)
        common = set(np.array(cube.dates)[usable].tolist())
        if common:
            rows += summarize_decay(cube, model_version, "common_panel", date_subset=common)
        else:
            print("[research] WARNING: no common panel — no date has every participating series "
                  "matured at h=%d, so cross-horizon comparisons are NOT period-controlled" % cap)

    df = pd.DataFrame(rows)
    path = os.path.join(_output_dir(output_dir), "signal_decay.csv")
    df.to_csv(path, index=False)
    print(f"[research] signal decay: {len(df)} rows -> {path}")
    return df


# ---------------------------------------------------------------------------
# (b) Walk-forward IC-weighted composite  — REPORT ONLY
# ---------------------------------------------------------------------------

TrainWindow = namedtuple(
    "TrainWindow", "fit_seq horizon train_end_date maturity_cutoff_date train_dates oos_dates")


def walk_forward_schedule(run_dates, calendar, horizon, mode=None, window=None, min_dates=None,
                          refit_every=None):
    """Build the fit schedule. A PURE function of dates — no prices, no scores, fully testable alone.

    THE LOOKAHEAD RULE LIVES HERE, ONCE. Training on every snapshot with `run_date <= T` looks right
    and is wrong: a snapshot taken 5 days before T has no known h=20 outcome yet, so including it
    means the "trailing" IC secretly contains information from after T. The correct filter is on the
    date each snapshot's outcome BECAME KNOWN — `maturity_cutoff_date`, which is exactly `horizon`
    sessions before T on the real calendar."""
    mode = mode or PARAMS["wf_train_mode"]
    window = window or PARAMS["wf_train_window_run_dates"]
    min_dates = min_dates or PARAMS["wf_train_min_run_dates"]
    refit_every = refit_every or PARAMS["wf_refit_every_run_dates"]

    run_dates = sorted(run_dates)
    cal_pos = {d: i for i, d in enumerate(calendar)}
    windows, seq = [], 0

    for i, train_end in enumerate(run_dates):
        pos = cal_pos.get(train_end)
        if pos is None or pos - horizon < 0:
            continue
        cutoff = calendar[pos - horizon]              # outcomes known on/before train_end
        eligible = [d for d in run_dates[:i + 1] if d <= cutoff]
        if mode == "rolling":
            eligible = eligible[-window:]
        if len(eligible) < min_dates:
            continue
        if windows and cal_pos.get(train_end, 0) - cal_pos.get(windows[-1].train_end_date, 0) < refit_every:
            continue
        oos_end = run_dates[i + refit_every] if i + refit_every < len(run_dates) else None
        oos = [d for d in run_dates[i + 1:] if oos_end is None or d < oos_end]
        if not oos:
            continue
        seq += 1
        windows.append(TrainWindow(fit_seq=seq, horizon=horizon, train_end_date=train_end,
                                   maturity_cutoff_date=cutoff, train_dates=eligible, oos_dates=oos))
    return windows


def fit_ic_weights(cube, window, variant, components=None):
    """Weights from the trailing ICs inside `window`. `window` is REQUIRED — you cannot assemble a
    training set without naming the maturity cutoff it was filtered on.

    Raises ValueError if any training date post-dates the cutoff, mirroring the date-join assertion
    in `evaluation.compute_forward_returns`: the invariant is enforced structurally, not by comment.

    Negative ICs are CLIPPED TO ZERO, never inverted. Every component in this system is defined
    "higher = better", so a negative weight silently redefines it; at these sample sizes a negative
    trailing IC is far more likely noise than a real inversion; and clipping fails conservatively —
    worst case a component is dropped, never actively bet against. Each clip is recorded so a
    PERSISTENTLY negative component still becomes visible in the artifact."""
    bad = [d for d in window.train_dates if d > window.maturity_cutoff_date]
    if bad:
        raise ValueError(
            f"lookahead in training set: {len(bad)} date(s) after the maturity cutoff "
            f"{window.maturity_cutoff_date} (e.g. {bad[:3]}) — a trailing IC built this way "
            f"contains outcomes that were not knowable at {window.train_end_date}")

    components = components or [c for c in cube.series if not c.startswith("score_")]
    hi = cube.horizons.index(window.horizon)
    train_mask = np.isin(np.array(cube.dates), list(window.train_dates))

    diagnostics, raw = {}, {}
    for c in components:
        si = cube.series.index(c)
        col = cube.ic[train_mask, si, hi]
        good = ~np.isnan(col)
        n = int(good.sum())
        vals = col[good].astype(np.float64)
        mean = float(vals.mean()) if n else None
        std = float(vals.std(ddof=1)) if n > 1 else None
        if n < PARAMS["wf_min_component_ic_days"] or mean is None:
            raw[c], diagnostics[c] = 0.0, {"mean_ic": mean, "std_ic": std, "n_ic_days": n,
                                           "raw_weight_input": None, "clipped": False,
                                           "unavailable": True}
            continue
        if variant == "ic_ratio":
            usable = std not in (None, 0) and n >= PARAMS["wf_ic_ratio_min_dates"]
            value = (mean / std) if usable else None
        else:
            value = mean
        clipped = value is not None and value < 0
        raw[c] = max(0.0, value) if value is not None else 0.0
        diagnostics[c] = {"mean_ic": mean, "std_ic": std, "n_ic_days": n,
                          "raw_weight_input": value, "clipped": bool(clipped),
                          "unavailable": value is None}

    total = sum(raw.values())
    if total <= 0:
        # Everything clipped away. Fall back to EQUAL weights over the available components and flag
        # it — never silently reinstate SCORE_WEIGHTS, which would disguise a failed fit as a result.
        avail = [c for c in components if not diagnostics[c]["unavailable"]] or components
        weights = {c: (1.0 / len(avail) if c in avail else 0.0) for c in components}
        degenerate = True
    else:
        weights = {c: v / total for c, v in raw.items()}
        degenerate = False
    return weights, {"diagnostics": diagnostics, "degenerate": degenerate}


def apply_weights(frame, weights):
    """Vectorized composite mirroring `scoring.compute_horizon_scores`' contract: SITOUT components
    may be absent and their weight renormalizes away; any MANDATORY component missing makes the
    whole score None (preserving v0.1's missing-input rule)."""
    cols = [c for c in weights if c in frame.columns and weights[c] > 0]
    if not cols:
        return pd.Series(np.nan, index=frame.index)
    vals = frame[cols].apply(pd.to_numeric, errors="coerce")
    w = pd.Series({c: weights[c] for c in cols}, dtype=float)
    present = vals.notna()
    mandatory = [c for c in cols if c not in SITOUT_COMPONENTS]
    weighted = (vals.fillna(0) * w).sum(axis=1)
    norm = (present * w).sum(axis=1)
    score = weighted / norm.replace(0, np.nan)
    if mandatory:
        score[~present[mandatory].all(axis=1)] = np.nan
    return score


def _daily_ic_series(rows, score_col, excess_col):
    """Per-day cross-sectional Spearman ICs, as a plain list."""
    ics = []
    for _d, sub in rows.groupby("run_date"):
        pair = rows.loc[sub.index, [score_col, excess_col]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) >= 3 and pair[score_col].nunique() > 1:
            ic = pair[score_col].rank().corr(pair[excess_col].rank(), method="pearson")
            if pd.notna(ic):
                ics.append(float(ic))
    return ics


def _score_out_of_sample(panel, fits, horizon):
    """Apply each fit's weights to its OWN out-of-sample dates and attach the realized excess return.

    A snapshot is scored by the fit whose training window closed before it — never by a fit trained
    on data that includes it."""
    pieces = []
    for w, weights in fits:
        sub = panel.frame[panel.frame["run_date"].isin(w.oos_dates)]
        if sub.empty:
            continue
        sub = sub.copy()
        sub[f"score_{horizon}d"] = apply_weights(sub, weights)
        sub[f"future_excess_return_{horizon}d"] = [
            forward_excess_vector(t, panel.benchmark_of.get(t, "SPY"), d, panel, horizon)[horizon - 1]
            for t, d in zip(sub["ticker"], sub["run_date"])]
        sub[f"max_drawdown_after_{horizon}d"] = np.nan
        pieces.append(sub)
    if not pieces:
        return None
    return pd.concat(pieces, ignore_index=True)


def run_walk_forward_analysis(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None):
    """IC-weighted composite scored strictly out-of-sample, against the hand-set config weights.

    REPORT ONLY. No model_version is bumped and no weight is deployed on the strength of this — a
    single walk-forward run over ~200 effective observations, searched across 2 variants x 4
    horizons, is precisely the setting where a flattering result shows up by chance.

    Writes walk_forward_weights.csv (every fit's weights AND its maturity cutoff, so the
    no-lookahead property is checkable by hand from the artifact) and walk_forward_comparison.csv."""
    model_version = model_version or PARAMS["model_version"]
    panel = load_panel(db_path, model_version)
    if panel is None:
        print(f"[research] no snapshots for {model_version}")
        return pd.DataFrame(), pd.DataFrame()

    horizons = PARAMS["wf_horizons"]
    cube = build_ic_cube(panel, SERIES_COLUMNS, max(horizons))
    baseline = SCORE_WEIGHTS_BY_VERSION.get(model_version, SCORE_WEIGHTS)
    weight_rows, comparison_rows = [], []

    for h in horizons:
        windows = walk_forward_schedule(cube.dates, panel.calendar, h)
        if not windows:
            print(f"[research] walk-forward h={h}: no fits possible with the history available")
            continue

        ic_variants = [v for v in PARAMS["wf_variants"] if v in ("ic_mean", "ic_ratio")]
        reg_variants = [v for v in PARAMS["wf_variants"] if v in ("ridge", "nnls")]
        fits_by_variant = {v: [] for v in PARAMS["wf_variants"]}
        fits_by_variant["baseline_config"] = []
        reg_components = [c for c in cube.series if not c.startswith("score_")]
        for w in windows:
            for variant in ic_variants:
                weights, diag = fit_ic_weights(cube, w, variant)
                for c, d in diag["diagnostics"].items():
                    weight_rows.append({
                        "model_version": model_version, "horizon": h, "variant": variant,
                        "fit_seq": w.fit_seq, "train_mode": PARAMS["wf_train_mode"],
                        "train_start_date": w.train_dates[0], "train_end_date": w.train_end_date,
                        # the two columns that make no-lookahead checkable from the artifact alone
                        "maturity_cutoff_date": w.maturity_cutoff_date,
                        "train_max_matured_on": max(w.train_dates),
                        "n_train_dates": len(w.train_dates), "component": c,
                        "mean_ic": d["mean_ic"], "std_ic": d["std_ic"], "n_ic_days": d["n_ic_days"],
                        "raw_weight_input": d["raw_weight_input"], "clipped": d["clipped"],
                        "weight": weights.get(c), "weights_degenerate": diag["degenerate"],
                        "oos_start_date": w.oos_dates[0], "oos_end_date": w.oos_dates[-1],
                        "n_oos_dates": len(w.oos_dates), "generated_at": _now_iso(),
                    })
                fits_by_variant[variant].append((w, weights))

            # Regression variants fit on the PANEL (standardized components -> realized forward
            # excess return) rather than on the IC cube, so they get their own loop. They enforce the
            # same maturity cutoff; see fit_regression_weights.
            for variant in reg_variants:
                weights, rdiag = fit_regression_weights(panel, w, variant, reg_components)
                for c in reg_components:
                    weight_rows.append({
                        "model_version": model_version, "horizon": h, "variant": variant,
                        "fit_seq": w.fit_seq, "train_mode": PARAMS["wf_train_mode"],
                        "train_start_date": w.train_dates[0], "train_end_date": w.train_end_date,
                        "maturity_cutoff_date": w.maturity_cutoff_date,
                        "train_max_matured_on": max(w.train_dates),
                        "n_train_dates": len(w.train_dates), "component": c,
                        "mean_ic": None, "std_ic": None, "n_ic_days": None,
                        "raw_weight_input": None, "clipped": None,
                        "weight": weights.get(c), "weights_degenerate": rdiag["degenerate"],
                        "n_train_rows": rdiag["n_train_rows"], "n_clipped": rdiag["n_clipped"],
                        "oos_start_date": w.oos_dates[0], "oos_end_date": w.oos_dates[-1],
                        "n_oos_dates": len(w.oos_dates), "generated_at": _now_iso(),
                    })
                fits_by_variant[variant].append((w, weights))
            # SCORE_WEIGHTS is keyed "score_20d", NOT "20d". Getting this wrong returned an empty
            # weight map, which apply_weights turned into an all-NaN column — so the baseline the
            # whole comparison exists to beat was silently absent rather than loudly broken.
            base_w = baseline.get(f"score_{h}d", {})
            if not base_w:
                raise KeyError(
                    f"no baseline weights for horizon {h} in SCORE_WEIGHTS_BY_VERSION"
                    f"[{model_version!r}]; keys are {sorted(baseline)} — refusing to emit a "
                    f"comparison with an empty baseline")
            fits_by_variant["baseline_config"].append((w, dict(base_w)))

        # Every variant is scored on the IDENTICAL out-of-sample dates, so the comparison is
        # apples-to-apples by construction rather than by hope.
        oos_dates = sorted({d for w in windows for d in w.oos_dates})
        for variant, fits in fits_by_variant.items():
            rows = _score_out_of_sample(panel, fits, h)
            if rows is None or rows.empty:
                continue
            # An all-NaN score column means this variant produced nothing; emitting its row anyway
            # would put a line of NaNs in the comparison and read as "measured, came out empty"
            # rather than "never computed".
            if rows[f"score_{h}d"].notna().sum() == 0:
                print(f"[research] WARNING: variant {variant} h={h} produced NO usable scores — "
                      f"omitting it rather than reporting a row of NaNs")
                continue
            dec = evaluation.build_decile_report(rows, f"{model_version}::{variant}", horizons=(h,))
            spread = next((r for r in dec if r["report_type"] == "decile_spread"), {})
            top10 = next((r for r in dec if r.get("selection") == "top_10"), {})
            ics = _daily_ic_series(rows, f"score_{h}d", f"future_excess_return_{h}d")
            mean_ic = float(np.mean(ics)) if ics else None
            std_ic = float(np.std(ics, ddof=1)) if len(ics) > 1 else None
            comparison_rows.append({
                "model_version": model_version, "horizon": h, "variant": variant,
                "n_oos_dates": len(oos_dates), "n_oos_snapshots": int(len(rows)),
                "oos_start_date": oos_dates[0], "oos_end_date": oos_dates[-1],
                "mean_daily_ic": mean_ic,
                "ic_t_stat_overlap_adj": evaluation._overlap_adjusted_t(mean_ic, std_ic, len(ics), h),
                "top_decile_avg_excess": spread.get("top_decile_avg_excess"),
                "bottom_decile_avg_excess": spread.get("bottom_decile_avg_excess"),
                "decile_spread_avg": spread.get("spread_avg"),
                "decile_spread_t_stat_overlap_adj": spread.get("spread_t_stat_overlap_adj"),
                "pct_days_spread_positive": spread.get("pct_days_spread_positive"),
                "top_10_avg_excess": top10.get("avg_future_excess_return"),
                "top_10_hit_rate_pct": top10.get("hit_rate_pct"),
                "sample_adequate": bool(len(oos_dates) >= PARAMS["wf_min_oos_dates"]),
                "generated_at": _now_iso(),
            })

    out = _output_dir(output_dir)
    wdf, cdf = pd.DataFrame(weight_rows), pd.DataFrame(comparison_rows)
    wdf.to_csv(os.path.join(out, "walk_forward_weights.csv"), index=False)
    cdf.to_csv(os.path.join(out, "walk_forward_comparison.csv"), index=False)
    print(f"[research] walk-forward: {len(wdf)} weight rows, {len(cdf)} comparison rows -> {out}")
    return wdf, cdf


# ---------------------------------------------------------------------------
# (c) Quality composite decomposition
# ---------------------------------------------------------------------------

def quality_legs():
    """The raw fields feeding quality, each with the sign the composite applies to it.

    Derived from FUNDAMENTAL_PERCENTILE_GROUPS rather than hardcoded, so a change to the composite
    cannot leave this decomposition quietly describing a composite that no longer exists."""
    spec = FUNDAMENTAL_PERCENTILE_GROUPS["quality_percentile"]
    legs = [(f, 1.0) for f in spec.get("fields", [])]
    legs += [(f, -1.0) for f in spec.get("invert_fields", [])]   # lower is better -> negate the rank
    return legs


def run_quality_decomposition(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                              horizons=None,
                              companions=("risk_component", "quality_component", "value_component")):
    """IC per LEG of the quality composite, plus a regime cross-check against risk_component.

    The question: quality_component's IC is negative and strengthens with horizon (-0.016 -> -0.062),
    inverted from the published prior. Two very different explanations:
      * REGIME — every leg is negative together because 2024-26 punished "boring safe companies" as a
        class. Then it is a market fact, not a defect, and risk_component (low-volatility, largely the
        same kind of name) should be negative over the SAME periods.
      * STRUCTURAL — one leg carries the negativity. The prime suspect is inverted debt_to_equity: it
        is the newest leg and it involves a sign flip, which is where sign errors hide.
    Each leg is ranked with the composite's own sign convention, so a leg's IC is directly comparable
    to the composite's. REPORT ONLY — no weight changes follow from this."""
    model_version = model_version or PARAMS["model_version"]
    horizons = horizons or list(evaluation.HORIZONS)
    legs = quality_legs()
    panel = load_panel(db_path, model_version, extra_columns=[f for f, _ in legs])
    if panel is None:
        print(f"[research] no snapshots for {model_version}")
        return pd.DataFrame(), pd.DataFrame()

    # Sign-adjusted leg columns, so each leg is ranked the way the composite ranks it.
    frame = panel.frame.copy()
    leg_cols = []
    for field, sign in legs:
        if field not in frame.columns:
            continue
        col = f"leg_{field}"
        frame[col] = pd.to_numeric(frame[field], errors="coerce") * sign
        leg_cols.append(col)
    panel = panel._replace(frame=frame)

    series = leg_cols + [c for c in companions if c in frame.columns]
    cube = build_ic_cube(panel, series, max(horizons))

    rows = []
    for si, s in enumerate(cube.series):
        field = s[4:] if s.startswith("leg_") else s
        sign = next((sg for f, sg in legs if f == field), None)
        for h in horizons:
            hi = cube.horizons.index(h)
            col = cube.ic[:, si, hi]
            good = ~np.isnan(col)
            n = int(good.sum())
            vals = col[good].astype(np.float64)
            mean = float(vals.mean()) if n else None
            rows.append({
                "model_version": model_version,
                "series": s, "kind": "quality_leg" if s.startswith("leg_") else "component",
                "field": field,
                "sign_applied": ("inverted (lower is better)" if sign == -1.0
                                 else ("direct" if sign == 1.0 else "")),
                "horizon": h, "mean_ic": mean,
                "median_ic": float(np.median(vals)) if n else None,
                "std_ic": float(vals.std(ddof=1)) if n > 1 else None,
                "pct_days_ic_positive": float((vals > 0).mean() * 100.0) if n else None,
                "n_days": n,
                "n_names_avg": float(cube.n_obs[good, si, hi].mean()) if n else 0.0,
                "ic_method": "mean_daily_cross_sectional_spearman",
                "generated_at": _now_iso(),
            })

    # The regime cross-check: do risk and quality ICs move TOGETHER across time? A high correlation
    # of their daily IC series is direct evidence of ONE shared driver rather than two separate faults.
    corr_rows = []
    if "risk_component" in cube.series and "quality_component" in cube.series:
        ri, qi = cube.series.index("risk_component"), cube.series.index("quality_component")
        for h in horizons:
            hi = cube.horizons.index(h)
            a, b = cube.ic[:, ri, hi], cube.ic[:, qi, hi]
            both = ~np.isnan(a) & ~np.isnan(b)
            if both.sum() >= 10:
                x, y = pd.Series(a[both].astype(float)), pd.Series(b[both].astype(float))
                pearson = float(x.corr(y))
                corr_rows.append({
                    "model_version": model_version, "horizon": h, "n_days": int(both.sum()),
                    "pearson_ic_corr": pearson,
                    "spearman_ic_corr": float(x.rank().corr(y.rank())),
                    "risk_mean_ic": float(x.mean()), "quality_mean_ic": float(y.mean()),
                    "interpretation": ("daily ICs move together -> consistent with ONE shared regime "
                                       "driver" if pearson > 0.3 else
                                       "daily ICs move largely independently -> a shared-regime "
                                       "explanation is NOT supported"),
                    "generated_at": _now_iso(),
                })

    out = _output_dir(output_dir)
    ldf, cdf = pd.DataFrame(rows), pd.DataFrame(corr_rows)
    ldf.to_csv(os.path.join(out, "quality_decomposition.csv"), index=False)
    cdf.to_csv(os.path.join(out, "quality_risk_ic_correlation.csv"), index=False)
    print(f"[research] quality decomposition: {len(ldf)} leg rows, {len(cdf)} correlation rows -> {out}")
    return ldf, cdf


# ---------------------------------------------------------------------------
# (e) SUE — standardized unexpected earnings, and the post-earnings-drift question
# ---------------------------------------------------------------------------

def _yoy_match(series, i, tol_days=45):
    """Index of the quarter ~1 year before series[i], or None.

    Matched on ACTUAL period_end distance rather than by stepping back four positions. Filers skip
    quarters in XBRL (NVDA and KO both have gaps in their 3-month EPS series because some quarters
    are only tagged year-to-date), so `i - 4` silently compares against the wrong season — which is
    the one error that would turn a seasonality artifact into a fake earnings surprise."""
    target = date.fromisoformat(series[i][0]) - timedelta(days=365)
    best, best_gap = None, None
    for j in range(i):
        gap = abs((date.fromisoformat(series[j][0]) - target).days)
        if gap <= tol_days and (best_gap is None or gap < best_gap):
            best, best_gap = j, gap
    return best


def sue_series(eps_series, min_history=6, surprise_window=8):
    """[(filed_date, period_end, sue, surprise, expected), ...] for each quarter that has enough
    history behind it.

    Expectation model: SEASONAL RANDOM WALK WITH DRIFT (Foster-Olsen-Shevlin). The naive forecast for
    this quarter is the same quarter a year ago, plus the average year-over-year change over recent
    quarters — that drift term is what stops a steadily-growing company from registering a "positive
    surprise" every single quarter. The surprise is then standardized by the standard deviation of
    the company's own recent surprises, which is what makes SUE comparable across a cross-section of
    companies with wildly different earnings volatility.

    Every quarter used in the expectation was filed BEFORE the quarter being scored, so a SUE stamped
    at quarter q's filing date uses only information public by then."""
    out = []
    surprises = []
    for i in range(len(eps_series)):
        j = _yoy_match(eps_series, i)
        if j is None:
            continue
        eps_now, eps_yoy = eps_series[i][2], eps_series[j][2]

        # drift = mean YoY change over prior quarters (strictly before i)
        drifts = []
        for k in range(i):
            kj = _yoy_match(eps_series, k)
            if kj is not None:
                drifts.append(eps_series[k][2] - eps_series[kj][2])
        drift = float(np.mean(drifts[-4:])) if drifts else 0.0

        expected = eps_yoy + drift
        surprise = eps_now - expected
        prior = surprises[-surprise_window:]
        # Standardizing needs a real dispersion estimate; with too little history the denominator is
        # noise and the SUE would be arbitrary, so the quarter simply has no SUE (invariant #2).
        if len(prior) >= min_history - 1:
            sd = float(np.std(prior, ddof=1))
            sue = (surprise / sd) if sd > 0 else None
        else:
            sue = None
        surprises.append(surprise)
        if sue is not None:
            out.append((eps_series[i][1], eps_series[i][0], float(sue), float(surprise),
                        float(expected)))
    return out


def build_sue_panel(panel, db_path, facts_index=None, tickers=None):
    """Attach point-in-time SUE columns to the panel frame.

    For each (ticker, run_date) the value used is the most recent quarter whose FILING date is on or
    before that run_date. A quarter ending 2025-03-31 typically is not public until early May, so
    keying on period_end instead would hand the model five weeks of foresight and manufacture exactly
    the drift this is trying to measure.

    Adds:
      sue                      — standardized unexpected earnings, carried forward from the filing
      sue_days_since_filing    — how stale it is; PEAD is documented to decay over 1-3 months, so
                                 this is what lets the decay be measured rather than assumed
      sue_fresh_63d            — SUE masked to the first ~3 months after the announcement
    """
    from src import edgar
    frame = panel.frame
    tickers = tickers or sorted(frame["ticker"].unique())
    by_ticker = {}
    for t in tickers:
        eps = edgar.quarterly_eps(t, db_path=db_path, facts_index=facts_index)
        s = sue_series(eps) if eps else []
        if s:
            by_ticker[t] = ([r[0] for r in s], s)      # filed dates (ascending) + rows

    sue_vals, age_vals = [], []
    for t, d in zip(frame["ticker"], frame["run_date"]):
        entry = by_ticker.get(t)
        if not entry:
            sue_vals.append(np.nan); age_vals.append(np.nan); continue
        filed_dates, rows = entry
        k = bisect_right(filed_dates, d) - 1          # newest filing at or before this run_date
        if k < 0:
            sue_vals.append(np.nan); age_vals.append(np.nan); continue
        sue_vals.append(rows[k][2])
        age_vals.append((date.fromisoformat(d) - date.fromisoformat(filed_dates[k])).days)

    frame = frame.copy()
    frame["sue"] = sue_vals
    frame["sue_days_since_filing"] = age_vals
    fresh = frame["sue"].where(frame["sue_days_since_filing"] <= 63)
    frame["sue_fresh_63d"] = fresh
    return panel._replace(frame=frame), by_ticker


def add_earnings_timing_columns(panel, sue_by_ticker):
    """Point-in-time earnings-calendar features derived from FILING dates.

    An important asymmetry, stated rather than glossed:
      * DAYS SINCE the last filing is genuinely point-in-time. The filing happened; its date is known.
      * DAYS UNTIL the NEXT filing is NOT. Taking it from the next actual filing in the table is a
        textbook lookahead — the model would know an announcement date before it was announced, and
        any "pre-earnings drift" measured that way is manufactured.
    So the pre-announcement window is built as a FORECAST from the company's own past filing cadence
    (median gap between its previous filings, all of which predate D). That is a real estimate a
    person could have made on the day, and it is labelled `expected_` to keep the distinction visible.
    """
    frame = panel.frame.copy()
    since, expected_until = [], []
    for t, d in zip(frame["ticker"], frame["run_date"]):
        entry = sue_by_ticker.get(t)
        if not entry:
            since.append(np.nan); expected_until.append(np.nan); continue
        filed_dates, _rows = entry
        k = bisect_right(filed_dates, d) - 1
        if k < 0:
            since.append(np.nan); expected_until.append(np.nan); continue
        days_since = (date.fromisoformat(d) - date.fromisoformat(filed_dates[k])).days
        since.append(days_since)
        # cadence estimated ONLY from gaps between filings already public at D
        past = filed_dates[:k + 1]
        gaps = [(date.fromisoformat(past[i]) - date.fromisoformat(past[i - 1])).days
                for i in range(max(1, len(past) - 8), len(past))]
        cadence = float(np.median(gaps)) if gaps else np.nan
        expected_until.append(cadence - days_since if cadence == cadence else np.nan)

    frame["days_since_earnings_filing"] = since
    frame["expected_days_to_next_filing"] = expected_until
    # Proximity signals: high value = close to the event. Signed so a positive IC means "names nearer
    # the event outperform", which is the direction the question is actually asking about.
    frame["post_earnings_proximity"] = -pd.Series(since, index=frame.index)
    frame["expected_pre_earnings_proximity"] = -pd.Series(expected_until, index=frame.index).abs()
    return panel._replace(frame=frame)


def run_short_horizon_research(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                               max_h=None):
    """Can fast-moving inputs produce the 5-60d signal the current slow feature set does not have?

    The decay curve showed composite IC of ~0.005-0.019 at 5-20d: effectively nothing. Every existing
    input is slow — TTM fundamentals, 200-day averages, 120-day momentum — so the absence of
    short-horizon signal may be a property of the INPUTS rather than of the market. Three probes:

      1. SUE. Post-earnings announcement drift is documented at 1-3 months, precisely the window
         where this system currently has nothing. SUE is stamped at the FILING date and carried
         forward, with a `_fresh_63d` variant restricted to the documented drift window.
      2. Short-term reversal. `short_momentum_component` rewards positive 5/10-day returns; the
         literature says that window mean-reverts. The raw returns are tested alongside the component,
         because a percentile transform can behave differently from what it was built from.
      3. Earnings timing as a SIGNAL rather than only a risk penalty — post-announcement proximity
         (point-in-time) and expected pre-announcement proximity (forecast from past cadence).

    REPORT ONLY."""
    model_version = model_version or PARAMS["model_version"]
    max_h = max_h or PARAMS["decay_max_horizon"]
    extra = ["return_5d", "return_10d", "return_20d", "short_momentum_component"]
    panel = load_panel(db_path, model_version, extra_columns=extra)
    if panel is None:
        print(f"[research] no snapshots for {model_version}")
        return pd.DataFrame()

    from src import edgar
    print("[research] pre-loading EDGAR EPS facts...", flush=True)
    # extra_tags is essential: the index is a TAG-FILTERED load and EPS is not among the ratio
    # concepts, so without it the index holds zero EPS facts and every SUE silently comes back empty.
    facts_index = edgar.build_facts_index(sorted(panel.frame["ticker"].unique()), db_path=db_path,
                                          extra_tags=edgar.EPS_TAGS)
    panel, sue_by_ticker = build_sue_panel(panel, db_path, facts_index=facts_index)
    panel = add_earnings_timing_columns(panel, sue_by_ticker)
    n_sue_rows = int(panel.frame["sue"].notna().sum())
    print(f"[research] SUE available for {len(sue_by_ticker)} tickers; "
          f"{n_sue_rows:,} of {len(panel.frame):,} rows carry a SUE", flush=True)
    # SUE is the headline of this analysis. Emitting a full report whose most important column is
    # silently empty reads as "measured, found nothing" rather than "never computed" - the same
    # failure mode that made the walk-forward baseline vanish. Fail loudly instead.
    if n_sue_rows == 0:
        raise RuntimeError(
            "no SUE values were computed for ANY row - refusing to emit a short-horizon report "
            "whose headline signal is entirely absent. Check that the facts index includes EPS "
            f"tags ({edgar.EPS_TAGS}) and that edgar_facts holds 3-month EPS periods.")

    # Reversal: the INVERTED sign of a rank IC is exactly its negation, so inverting is reported as a
    # derived column rather than measured twice — pretending otherwise would dress one number up as two.
    series = ["sue", "sue_fresh_63d", "short_momentum_component", "return_5d", "return_10d",
              "return_20d", "post_earnings_proximity", "expected_pre_earnings_proximity"]
    series = [s for s in series if s in panel.frame.columns]
    cube = build_ic_cube(panel, series, max_h)

    rows = []
    for si, s in enumerate(cube.series):
        for hi, h in enumerate(cube.horizons):
            col = cube.ic[:, si, hi]
            good = ~np.isnan(col)
            n = int(good.sum())
            if not n:
                continue
            vals = col[good].astype(np.float64)
            mean = float(vals.mean())
            std = float(vals.std(ddof=1)) if n > 1 else None
            rows.append({
                "model_version": model_version, "series": s, "horizon": h,
                "mean_ic": mean, "median_ic": float(np.median(vals)), "std_ic": std,
                "ic_if_sign_inverted": -mean,      # exact negation, stated explicitly
                "ic_t_stat_overlap_adj": evaluation._overlap_adjusted_t(mean, std, n, h),
                "pct_days_ic_positive": float((vals > 0).mean() * 100.0),
                "n_days": n, "n_names_avg": float(cube.n_obs[good, si, hi].mean()),
                "sample_adequate": bool(n >= PARAMS["decay_min_days"]),
                "ic_method": "mean_daily_cross_sectional_spearman",
                "generated_at": _now_iso(),
            })

    df = pd.DataFrame(rows)
    path = os.path.join(_output_dir(output_dir), "short_horizon_signals.csv")
    df.to_csv(path, index=False)
    print(f"[research] short-horizon signals: {len(df)} rows -> {path}")
    return df


# ---------------------------------------------------------------------------
# (f) Size-bucket decay comparison - the v0.5 question
# ---------------------------------------------------------------------------

def load_size_buckets(watchlist_path=None):
    """{ticker: size_bucket} from the watchlist. Buckets come from the source index (S&P 500/400/600),
    which is the closest thing to a market-cap classification available without a paid data source."""
    path = watchlist_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.csv")
    wl = pd.read_csv(path)
    if "size_bucket" not in wl.columns:
        return {}
    return {t: b for t, b in zip(wl["ticker"], wl["size_bucket"])
            if isinstance(b, str) and b}


def run_size_bucket_decay(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                          max_h=None, watchlist_path=None):
    """Is the 5-40d signal band empty OUTSIDE the S&P 500?

    The decay curve measured composite IC of 0.005-0.019 at 5-20d - effectively nothing - but only on
    large caps, the most-watched and most-arbitraged segment there is. If short-horizon inefficiency
    survives anywhere, it should survive where fewer people are looking. So the pre-registered reading
    is small > mid > large in the 5-40d band. A FLAT result says the emptiness is a property of the
    market (or of these features), not of attention.

    THE BENCHMARK CONTROL, which is what makes this comparison legitimate: large caps are benchmarked
    to sector ETFs while mid/small are benchmarked to broad size ETFs, because no liquid mid/small
    sector ETF family exists. Comparing buckets under different benchmark regimes would confound the
    result. So every bucket is measured against ONE COMMON benchmark here (SIZE_BUCKET_BENCHMARK), and
    that choice is provably harmless: a cross-sectional rank correlation computed WITHIN a group
    cannot be changed by subtracting a per-date constant that every member of the group shares.

    REPORT ONLY."""
    model_version = model_version or PARAMS["model_version"]
    max_h = max_h or PARAMS["decay_max_horizon"]
    buckets = load_size_buckets(watchlist_path)
    if not buckets:
        print("[research] no size_bucket column in the watchlist - run the universe expansion first")
        return pd.DataFrame()

    panel = load_panel(db_path, model_version)
    if panel is None:
        print(f"[research] no snapshots for {model_version}")
        return pd.DataFrame()

    frame = panel.frame.copy()
    frame["size_bucket"] = frame["ticker"].map(buckets)
    frame = frame[frame["size_bucket"].notna()]

    rows = []
    for bucket in sorted(frame["size_bucket"].unique()):
        sub = frame[frame["size_bucket"] == bucket]
        common_bench = SIZE_BUCKET_BENCHMARK.get(bucket)
        if common_bench not in panel.closes:
            print(f"[research] WARNING: benchmark {common_bench} for bucket '{bucket}' has no price "
                  f"history - skipping the bucket rather than silently using a different benchmark")
            continue
        # every name in the bucket measured against the SAME benchmark (see docstring)
        bench_of = {t: common_bench for t in sub["ticker"].unique()}
        bucket_panel = panel._replace(frame=sub, benchmark_of=bench_of)
        cube = build_ic_cube(bucket_panel, SERIES_COLUMNS, max_h,
                             date_stride=PARAMS["decay_date_stride"])
        if not cube.dates:
            print(f"[research] bucket '{bucket}': no dates cleared the min-names gate")
            continue
        bucket_rows = summarize_decay(cube, model_version, "all_available")
        for r in bucket_rows:
            r["size_bucket"] = bucket
            r["common_benchmark"] = common_bench
            r["n_tickers"] = int(sub["ticker"].nunique())
        rows += bucket_rows
        print(f"[research] bucket '{bucket}': {sub['ticker'].nunique()} tickers, "
              f"{len(cube.dates)} dates, benchmark {common_bench}", flush=True)

    df = pd.DataFrame(rows)
    path = os.path.join(_output_dir(output_dir), "signal_decay_by_size.csv")
    df.to_csv(path, index=False)
    print(f"[research] size-bucket decay: {len(df)} rows -> {path}")
    return df


# ---------------------------------------------------------------------------
# Regression-fitted weights (Job 3): ridge and non-negative least squares
# ---------------------------------------------------------------------------

def ridge_weights(X, y, alpha):
    """Closed-form L2-regularized least squares: w = (X'X + alpha*I)^-1 X'y.

    Regularization is not optional here. With ~17 correlated components and only a few hundred
    effective observations, an unpenalized fit puts enormous offsetting weights on collinear
    momentum terms — a textbook way to fit noise and produce a beautiful in-sample result that dies
    out of sample. `solve` is used rather than an explicit inverse, for numerical stability."""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    A = X.T @ X + alpha * np.eye(X.shape[1])
    b = X.T @ y
    try:
        return np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(A, b, rcond=None)[0]


def nnls_weights(X, y, max_iter=500, tol=1e-10):
    """Non-negative least squares by projected coordinate descent.

    Implemented rather than imported: scipy is deliberately not a dependency of this project (the
    same reason Spearman is done as rank-then-Pearson throughout), and at ~17 features this
    converges in milliseconds.

    Non-negativity is the point, not a convenience. Every component is defined "higher = better", so
    a negative coefficient silently redefines what the component means. Constraining the fit is also
    more honest than clipping a negative coefficient AFTER an unconstrained fit: clipping leaves the
    remaining weights at values that were only optimal in the presence of the negative one."""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n_feat = X.shape[1]
    w = np.zeros(n_feat, dtype=np.float64)
    XtX, Xty = X.T @ X, X.T @ y
    diag = np.diag(XtX).copy()
    diag[diag <= 0] = 1e-12
    for _ in range(max_iter):
        max_step = 0.0
        for j in range(n_feat):
            partial = Xty[j] - XtX[j] @ w + XtX[j, j] * w[j]
            new = max(0.0, partial / diag[j])
            max_step = max(max_step, abs(new - w[j]))
            w[j] = new
        if max_step < tol:
            break
    return w


def _standardized_training_matrix(panel, window, components, horizon):
    """(X, y) for a regression fit, from snapshots whose outcome was knowable at the train end.

    X holds per-date cross-sectionally standardized component values; y is realized forward excess
    return. Standardizing WITHIN each date is what stops a high-volatility regime from dominating
    the fit merely because its numbers are larger."""
    train = panel.frame[panel.frame["run_date"].isin(set(window.train_dates))]
    if train.empty:
        return None, None
    xs, ys = [], []
    for d, sub in train.groupby("run_date"):
        vals = sub[components].apply(pd.to_numeric, errors="coerce")
        fwd = np.array([forward_excess_vector(t, panel.benchmark_of.get(t, PARAMS["calendar_ticker"]),
                                              d, panel, horizon)[horizon - 1]
                        for t in sub["ticker"]], dtype=np.float64)
        ok = (~vals.isna().any(axis=1)).to_numpy() & ~np.isnan(fwd)
        if ok.sum() < 5:
            continue
        v = vals.to_numpy()[ok]
        mu, sd = v.mean(axis=0), v.std(axis=0, ddof=0)
        sd[sd == 0] = 1.0
        xs.append((v - mu) / sd)
        ys.append(fwd[ok])
    if not xs:
        return None, None
    return np.vstack(xs), np.concatenate(ys)


def fit_regression_weights(panel, window, variant, components, alpha=None):
    """Weights fitted by regressing realized forward excess return on standardized components.

    Carries the SAME structural lookahead guard as `fit_ic_weights`: a training set containing a date
    past the maturity cutoff is a hard error, not a warning. That cutoff is the whole difference
    between a trailing fit and a clairvoyant one, so it is enforced in both fitting paths rather
    than trusted to the caller."""
    bad = [d for d in window.train_dates if d > window.maturity_cutoff_date]
    if bad:
        raise ValueError(
            f"lookahead in training set: {len(bad)} date(s) after the maturity cutoff "
            f"{window.maturity_cutoff_date} (e.g. {bad[:3]}) - a regression fit this way is "
            f"trained on outcomes that were not knowable at {window.train_end_date}")

    alpha = PARAMS["wf_ridge_alpha"] if alpha is None else alpha

    # A component that is null EVERYWHERE in the training window cannot participate, and must not
    # VETO the fit. The training matrix requires every listed component to be present on a row, so a
    # single all-null component drops 100% of rows - and the fit then silently produces nothing.
    # short_interest_component is exactly that case: it is live-only (FINRA) and never backfills, so
    # it is null on every one of the 779k backfilled rows. This is the same failure the decay
    # analysis already hit with its common panel; the rule is the same one, applied here too.
    train_rows = panel.frame[panel.frame["run_date"].isin(set(window.train_dates))]
    usable = [c for c in components
              if c in train_rows.columns and train_rows[c].notna().any()]
    unavailable = [c for c in components if c not in usable]
    if not usable:
        return ({c: 0.0 for c in components},
                {"degenerate": True, "n_train_rows": 0, "n_clipped": 0,
                 "n_unavailable": len(unavailable), "unavailable": unavailable})

    X, y = _standardized_training_matrix(panel, window, usable, window.horizon)
    if X is None or len(y) < PARAMS["wf_min_regression_rows"]:
        return ({c: 0.0 for c in components},
                {"degenerate": True, "n_train_rows": 0 if y is None else int(len(y)),
                 "n_clipped": 0, "n_unavailable": len(unavailable), "unavailable": unavailable})

    if variant == "ridge":
        coef = ridge_weights(X, y, alpha)
        # ridge is unconstrained, so negatives are clipped for the same reason ic_mean clips them:
        # a negative weight redefines a "higher = better" component. Recorded, never silent.
        clipped = int((coef < 0).sum())
        coef = np.maximum(coef, 0.0)
    else:
        coef = nnls_weights(X, y)
        clipped = 0

    total = float(coef.sum())
    if total <= 0:
        # Nothing survived. Fall back to EQUAL weights and flag it - never to SCORE_WEIGHTS, because
        # silently reintroducing the baseline would make the fitted variant appear to match the
        # baseline on its own merits.
        return ({c: (1.0 / len(usable) if c in usable else 0.0) for c in components},
                {"degenerate": True, "n_train_rows": int(len(y)), "n_clipped": clipped,
                 "n_unavailable": len(unavailable), "unavailable": unavailable})
    weights = {c: 0.0 for c in components}          # unavailable components stay at zero, flagged
    weights.update({c: float(w) / total for c, w in zip(usable, coef)})
    return (weights, {"degenerate": False, "n_train_rows": int(len(y)), "n_clipped": clipped,
                      "n_unavailable": len(unavailable), "unavailable": unavailable})


# ---------------------------------------------------------------------------
# (f) SEC Form 4 insider transactions — REPORT ONLY
# ---------------------------------------------------------------------------

# PRE-REGISTERED READING, written before the numbers were seen (the standing discipline from
# ROADMAP: state the expected pattern first, so a surprising result triggers a bug hunt rather than
# a celebration).
#
#   The published anomaly says OPEN-MARKET INSIDER BUYING predicts positive abnormal returns over
#   roughly 1-12 months, is stronger for smaller companies, and is stronger for officers and
#   directors than for 10% holders. Insider SELLING is much weaker and noisier, because selling is
#   driven by diversification, tax and pre-scheduled plans as often as by information.
#
#   So: IC on the buy-side measures should be POSITIVE and should GROW with horizon, peaking around
#   60-120d. If instead the signal is strongest at 1-5d, or the sign is negative, that is a reason
#   to suspect the date join before believing the result — the same rule CLAUDE.md applies to
#   momentum.
INSIDER_HORIZONS = [5, 20, 60, 120]


def _insider_panel_frame(panel, index, window_days=90):
    """(run_date, ticker, insider features, forward excess returns) for every covered snapshot.

    Rows whose date lies past the end of ingested coverage are DROPPED, never zero-filled. A gap in
    the data and a genuine absence of insider buying are different facts, and writing both as 0
    would manufacture a "no insider interest" signal out of a publication lag."""
    from src.insider import INSIDER_FEATURE_COLUMNS, features_from_index

    max_h = max(INSIDER_HORIZONS)
    records, skipped_uncovered = [], 0
    for run_date, ticker, benchmark in zip(panel.frame["run_date"], panel.frame["ticker"],
                                           panel.frame["benchmark"]):
        feats = features_from_index(index, ticker, run_date, window_days=window_days)
        if feats["coverage_missing"]:
            skipped_uncovered += 1
            continue
        fwd = forward_excess_vector(ticker, benchmark, run_date, panel, max_h)
        rec = {"run_date": run_date, "ticker": ticker}
        for c in INSIDER_FEATURE_COLUMNS:
            rec[c] = feats.get(c)
        for h in INSIDER_HORIZONS:
            v = fwd[h - 1]
            rec["excess_%dd" % h] = float(v) if not np.isnan(v) else None
        records.append(rec)
    print("[research] insider panel: %d rows, %d dropped as outside coverage (never zero-filled)"
          % (len(records), skipped_uncovered))
    return pd.DataFrame(records)


def run_insider_research(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                         window_days=90):
    """Does open-market insider buying predict forward excess return? REPORT ONLY.

    Two views, because they answer different questions:
      * insider_ic.csv — cross-sectional Spearman IC per feature per horizon. Asks whether the
        ORDERING is informative, directly comparable with every other factor in this project.
      * insider_event_study.csv — the binary version: names with at least one purchase in the
        trailing window against names with none. Asks whether the EVENT is tradeable, which is the
        form the anomaly is actually published in and is far easier to act on.
    """
    from src import insider as insider_mod

    model_version = model_version or PARAMS["model_version"]
    panel = load_panel(db_path, model_version)
    if panel is None:
        print("[research] no snapshots for %s" % model_version)
        return pd.DataFrame()
    index = insider_mod.build_insider_index(db_path=db_path)
    if not index.by_ticker:
        raise RuntimeError(
            "insider store is empty — run the insider ingest first. Refusing to report 'no signal' "
            "from an empty table, which is indistinguishable from a real null.")
    print("[research] insider coverage %s .. %s, %d tickers with P/S activity"
          % (index.coverage_start, index.coverage_end, len(index.by_ticker)))

    frame = _insider_panel_frame(panel, index, window_days=window_days)
    if frame.empty:
        print("[research] no covered snapshots — nothing to measure")
        return pd.DataFrame()

    ic_rows, event_rows = [], []
    for h in INSIDER_HORIZONS:
        excess_col = "excess_%dd" % h
        matured = frame[frame[excess_col].notna()]
        for feat in insider_mod.INSIDER_FEATURE_COLUMNS:
            daily = []
            for _, sub in matured.groupby("run_date"):
                s = sub[[feat, excess_col]].dropna()
                # A day where every name has the same value (usually zero) carries no ordering
                # information at all. Including it would report an IC of 0 for a day that measured
                # nothing, dragging the average toward zero and hiding whatever the active days say.
                if len(s) < PARAMS["decay_min_names_per_day"] or s[feat].nunique() < 2:
                    continue
                daily.append(evaluation._spearman_ic(s, feat, excess_col))
            daily = [v for v in daily if v is not None and not pd.isna(v)]
            stats = evaluation._aggregate_daily(pd.Series(daily, dtype=float))
            ic_rows.append({
                "model_version": model_version, "feature": feat, "horizon": h,
                "window_days": window_days,
                "ic_mean": stats["mean"], "ic_median": stats["median"],
                "ic_pct_positive": stats["pct_positive"], "n_days": stats["n_days"],
                "overlap_adjusted_t": evaluation._overlap_adjusted_t(
                    stats["mean"], stats["std"], stats["n_days"], h),
                "effective_independent_n": (round(stats["n_days"] / float(h), 1)
                                            if stats["n_days"] else 0),
                "generated_at": _now_iso(),
            })

        # Event study. Per-day means FIRST, then averaged across days — pooling every (name, date)
        # row would weight a day with 40 buyers 40x a day with one, and would treat overlapping
        # forward windows as independent observations.
        buy_col = "insider_buy_count_%dd" % window_days
        day_diffs, day_hits, n_events = [], [], 0
        for _, sub in matured.groupby("run_date"):
            hit = sub[sub[buy_col] > 0]
            miss = sub[sub[buy_col] == 0]
            if len(hit) < 3 or len(miss) < PARAMS["decay_min_names_per_day"]:
                continue
            day_diffs.append(float(hit[excess_col].mean() - miss[excess_col].mean()))
            day_hits.append(float((hit[excess_col] > 0).mean() * 100.0))
            n_events += len(hit)
        stats = evaluation._aggregate_daily(pd.Series(day_diffs, dtype=float))
        event_rows.append({
            "model_version": model_version, "horizon": h, "window_days": window_days,
            "n_days": stats["n_days"], "n_name_days_with_a_purchase": n_events,
            "mean_excess_spread_pct": ((stats["mean"] * 100.0)
                                       if stats["mean"] is not None else None),
            "median_excess_spread_pct": ((stats["median"] * 100.0)
                                         if stats["median"] is not None else None),
            "pct_of_days_positive": stats["pct_positive"],
            "hit_rate_pct": float(np.mean(day_hits)) if day_hits else None,
            "overlap_adjusted_t": evaluation._overlap_adjusted_t(
                stats["mean"], stats["std"], stats["n_days"], h),
            "effective_independent_n": (round(stats["n_days"] / float(h), 1)
                                        if stats["n_days"] else 0),
            "survivorship_biased": True,
            "coverage_first_filed": index.coverage_start,
            "coverage_last_filed": index.coverage_end,
            "generated_at": _now_iso(),
        })

    out_dir = _output_dir(output_dir)
    ic_df = pd.DataFrame(ic_rows)
    ev_df = pd.DataFrame(event_rows)
    ic_df.to_csv(os.path.join(out_dir, "insider_ic.csv"), index=False)
    ev_df.to_csv(os.path.join(out_dir, "insider_event_study.csv"), index=False)
    print("[research] insider IC: %d rows -> insider_ic.csv" % len(ic_df))
    print("[research] insider event study: %d rows -> insider_event_study.csv" % len(ev_df))
    return ic_df
