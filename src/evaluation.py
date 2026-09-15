"""Stage 3 — performance evaluation loop.

For every stored feature_snapshots row (run_date D, ticker T), join forward to T's own
real future price history (never by row position in a mixed-ticker table — a lookahead
leak via wrong-ticker bleed-through is the single most dangerous silent failure mode per
CLAUDE.md) and compute future returns / excess returns vs T's benchmark, then aggregate
into output/performance_review.csv: per (horizon, score-label) bucket stats, plus
per-component Pearson/Spearman correlation against future excess return (an information
coefficient) with descriptive, never-auto-applied suggested weight-change notes.
"""

import math
import os

import pandas as pd

from src import scoring, storage
from src.config import (FROZEN_MODEL_VERSIONS, PARAMS, SCORE_WEIGHTS, SCORE_WEIGHTS_BY_VERSION,
                        SITOUT_COMPONENTS)

HORIZONS = (5, 20, 60, 120)
# Spec only defines a forward max-drawdown metric for these two horizons.
DRAWDOWN_HORIZONS = (20, 60)

_COMPONENT_COLUMNS = [c for c in storage.SCORE_COLUMNS if not c.startswith("score_")]


def trading_calendar(db_path=storage.DEFAULT_DB_PATH, calendar_ticker=None):
    """The master NYSE session calendar (ascending) — the calendar ticker's cached price dates.

    Promoted here so evaluation, journal and research all read ONE calendar. A second, subtly
    different session list is exactly how a maturity bug gets in: two modules disagreeing about which
    day is D+20 will disagree about which snapshots are ripe to score."""
    ticker = calendar_ticker or PARAMS["calendar_ticker"]
    return [r["date"] for r in storage.load_price_history(ticker, db_path=db_path)]


def maturity_date(calendar, snapshot_date, horizon):
    """The real trading date on which a snapshot's `horizon`-day forward return first becomes KNOWN.

    Returns None when D+horizon has not elapsed yet (the guardrail — never evaluate a horizon whose
    forward data doesn't exist). Raises ValueError if the resolved date is not strictly after the
    snapshot, mirroring the date-join assertion in compute_forward_returns: any code that reasons
    about maturity gets the same protection as the code that computes returns."""
    try:
        idx = calendar.index(snapshot_date)
    except ValueError:
        return None
    target = idx + horizon
    if target >= len(calendar):
        return None
    resolved = calendar[target]
    if resolved <= snapshot_date:
        raise ValueError(
            f"maturity bug: D+{horizon} for {snapshot_date} resolved to {resolved}, which does not "
            f"come after it — never trust a maturity computed this way")
    return resolved


def _date_index(history):
    """history: list of dicts (storage.load_price_history output, date-sorted ascending).
    Returns (dates: list[str], closes: list[float], date->index dict) for O(1) lookups."""
    dates = [row["date"] for row in history]
    closes = [row["close"] for row in history]
    return dates, closes, {d: i for i, d in enumerate(dates)}


def _forward_return(closes, idx, n):
    """closes[idx+n] / closes[idx] - 1, or None if D+n hasn't elapsed yet (guardrail —
    never evaluate a horizon whose forward data doesn't exist)."""
    if idx is None or idx + n >= len(closes):
        return None
    base = closes[idx]
    if not base:
        return None
    return closes[idx + n] / base - 1.0


def _max_drawdown_after(closes, idx, n):
    """Positive-magnitude peak-to-trough decline over the n sessions following idx
    (inclusive of the snapshot day as the starting peak candidate)."""
    if idx is None or idx + n >= len(closes):
        return None
    window = closes[idx: idx + n + 1]
    if len(window) < 2:
        return None
    peak = window[0]
    max_dd = 0.0
    for c in window:
        peak = max(peak, c)
        if peak:
            max_dd = max(max_dd, (peak - c) / peak)
    return max_dd * 100.0


def compute_forward_returns(snapshot_date, ticker_dates, ticker_closes, ticker_date_idx,
                             benchmark_dates, benchmark_closes, benchmark_date_idx):
    """Locate snapshot_date within the ticker's OWN date-sorted series (never the
    benchmark's or another ticker's row positions) and compute forward/excess returns +
    forward max drawdown for every horizon. Returns a flat dict; any horizon whose D+N
    hasn't elapsed yet is None for that horizon (guardrail), not an error."""
    out = {}
    idx_t = ticker_date_idx.get(snapshot_date)
    idx_b = benchmark_date_idx.get(snapshot_date)

    for n in HORIZONS:
        fut_ret = _forward_return(ticker_closes, idx_t, n)
        fut_bench_ret = _forward_return(benchmark_closes, idx_b, n)
        excess = fut_ret - fut_bench_ret if (fut_ret is not None and fut_bench_ret is not None) else None
        out[f"future_return_{n}d"] = fut_ret
        out[f"future_benchmark_return_{n}d"] = fut_bench_ret
        out[f"future_excess_return_{n}d"] = excess

        if fut_ret is not None:
            forward_date = ticker_dates[idx_t + n]
            if forward_date <= snapshot_date:
                raise ValueError(
                    f"date-join bug: resolved forward date {forward_date} for horizon {n}d "
                    f"does not come after snapshot_date {snapshot_date} — never trust a "
                    f"forward return computed this way"
                )

    for n in DRAWDOWN_HORIZONS:
        out[f"max_drawdown_after_{n}d"] = _max_drawdown_after(ticker_closes, idx_t, n)

    return out


def evaluate_all_snapshots(db_path=storage.DEFAULT_DB_PATH, model_version=None, live_only=False):
    """Load every snapshot for model_version, join each one forward by real trading
    date, and return the list of snapshot dicts augmented with forward/excess returns.
    Snapshots whose ticker/benchmark history can't be loaded, or whose run_date isn't
    found in the ticker's own price history (shouldn't happen given how snapshots are
    created — defensive only), are skipped with a warning rather than crashing."""
    model_version = model_version or PARAMS["model_version"]
    snapshots = storage.load_all_snapshots(db_path, model_version=model_version)
    if live_only:
        # Only rows the model produced in real time. Backfilled rows are immutable reconstructions and
        # vastly outnumber live ones (~1.3M vs ~23k), so restricting to live is what makes the
        # cross-version continuity view affordable at all.
        snapshots = [r for r in snapshots if not int(r.get("backfilled") or 0)]
    if not snapshots:
        return []

    history_cache = {}

    def _get_index(ticker):
        if ticker not in history_cache:
            hist = storage.load_price_history(ticker, db_path=db_path)
            history_cache[ticker] = _date_index(hist) if hist else None
        return history_cache[ticker]

    # THE THIRD MEASURE. Excess-vs-sector-benchmark answers "does the ranking have skill" — the right
    # question for BUILDING the model, because subtracting the sector strips out beta and leaves only
    # the ordering. It is the wrong question for DECIDING, and it flatters: a stock that falls 15%
    # while its sector falls 20% is a "hit", and you are still down 15%.
    #
    # The decision a person actually faces is "this stock, or the index fund I would otherwise buy".
    # So the index's own forward return is computed once per run_date and carried alongside, giving
    # three readings that are cheap to produce and disagree informatively:
    #   future_return_Nd            -> did it make money at all
    #   future_excess_vs_index_Nd   -> was it worth doing instead of just buying SPY
    #   future_excess_return_Nd     -> does the ranking have skill (sector-neutral)
    index_ticker = PARAMS["calendar_ticker"]
    index_idx = _get_index(index_ticker)
    index_forward_cache = {}

    def _index_forward(run_date):
        if run_date not in index_forward_cache:
            out = {}
            if index_idx is not None:
                _dates, closes, dmap = index_idx
                i = dmap.get(run_date)
                for n in HORIZONS:
                    out[n] = _forward_return(closes, i, n)
            index_forward_cache[run_date] = out
        return index_forward_cache[run_date]

    evaluated = []
    for row in snapshots:
        ticker, benchmark, run_date = row["ticker"], row["benchmark"], row["run_date"]
        t_idx, b_idx = _get_index(ticker), _get_index(benchmark)
        if t_idx is None or b_idx is None:
            print(f"[evaluation] WARNING: skipping {ticker} @ {run_date} — missing price history for ticker or benchmark")
            continue
        ticker_dates, ticker_closes, ticker_date_idx = t_idx
        benchmark_dates, benchmark_closes, benchmark_date_idx = b_idx
        if run_date not in ticker_date_idx:
            print(f"[evaluation] WARNING: skipping {ticker} @ {run_date} — run_date not found in its own cached price history")
            continue

        forward = compute_forward_returns(
            run_date, ticker_dates, ticker_closes, ticker_date_idx,
            benchmark_dates, benchmark_closes, benchmark_date_idx,
        )
        for key, value in forward.items():
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                print(f"[evaluation] WARNING: {key} for {ticker} @ {run_date} is {value} — excluding from evaluation")
                forward[key] = None

        merged = dict(row)
        merged.update(forward)

        index_fwd = _index_forward(run_date)
        for n in HORIZONS:
            ir = index_fwd.get(n)
            tr = forward.get(f"future_return_{n}d")
            merged[f"future_index_return_{n}d"] = ir
            merged[f"future_excess_vs_index_{n}d"] = (
                tr - ir if (tr is not None and ir is not None) else None)
        evaluated.append(merged)

    return evaluated


def _suggested_weight_note(component, horizon_key, ic, current_weight):
    if ic is None or (isinstance(ic, float) and math.isnan(ic)) or current_weight is None:
        return None
    if ic > 0.10:
        return (f"{component} IC={ic:.2f} is meaningfully positive vs its {current_weight:.0%} "
                f"weight in {horizon_key} — consider increasing")
    if ic < -0.05:
        return (f"{component} IC={ic:.2f} is negative vs its {current_weight:.0%} "
                f"weight in {horizon_key} — consider decreasing or removing")
    return (f"{component} IC={ic:.2f} is weak — its {current_weight:.0%} "
            f"weight in {horizon_key} doesn't look clearly mis-sized")


def _spearman_ic(sub, comp, excess_col):
    """Spearman IC = Pearson correlation of the ranks — computed this way so the project
    doesn't need scipy (pandas' method='spearman' calls into it)."""
    return sub[comp].rank().corr(sub[excess_col].rank(), method="pearson")


def has_stale_fundamentals(row):
    """The single definition of a row whose FUNDAMENTALS are not point-in-time.

    Was `is_recovered`, which tested `recovered == 1` alone. That proxy held while every fundamental
    came from yfinance (current-only, so a reconstructed day necessarily carried a LATER fetch), and it
    stopped holding at v0.4: EDGAR resolves fundamentals from filings gated on filed_date <= D, so a
    v0.4 row is genuinely point-in-time EVEN ON A RECOVERED DAY. Keying off `recovered` there would
    throw away perfectly valid evidence from the very factors v0.4 exists to validate.

    So the test is now: is this row's fundamental data point-in-time? `fundamentals_pit` says yes
    outright (EDGAR). Otherwise fall back to the old rule — a recovered yfinance row is stale.
    Shared by 4a (the fundamental-factor IC, via _ic_base) and Sections 2/3 (the hit-rate buckets, via
    journal._grade_all_cohorts) so the two exclusions can never drift apart."""
    if int(row.get("fundamentals_pit") or 0) == 1:
        return False
    return int(row.get("recovered") or 0) == 1


# Back-compat alias: `is_recovered` was the public name before v0.4 generalized the rule.
is_recovered = has_stale_fundamentals


def exclude_recovered(rows):
    """Drop rows with non-point-in-time fundamentals from an iterable of evaluated row-dicts. Used by
    the journal's Section 2/3 grading; mirrors _ic_base's fundamental-IC exclusion (same
    has_stale_fundamentals rule, one source of truth)."""
    return [r for r in rows if not has_stale_fundamentals(r)]


def _ic_base(frame, comp):
    """The rows a component's IC is computed over. For the three fundamental factors ONLY
    (SITOUT_COMPONENTS: value/quality/short-interest), rows whose fundamentals are NOT point-in-time
    are dropped — including them would be a lookahead leak in the very metric that validates those
    factors (CLAUDE.md invariant #1). Every price/volume component is strictly point-in-time even on a
    recovered day, so it keeps all rows. Same rule as has_stale_fundamentals(), applied column-wise:
    a v0.4 EDGAR row (fundamentals_pit=1) is KEPT even when recovered=1; a v0.3 recovered row is not."""
    if comp not in SITOUT_COMPONENTS or "recovered" not in frame.columns:
        return frame
    stale = frame["recovered"].fillna(0).astype(int) == 1
    if "fundamentals_pit" in frame.columns:
        stale &= frame["fundamentals_pit"].fillna(0).astype(int) != 1
    return frame[~stale]


def assign_deciles(scores, n_buckets=None):
    """Cross-sectional decile within ONE day's scores. 1 = BEST, n_buckets = worst.

    Ties SHARE a decile (`rank(method="average")`). Identical scores are indistinguishable to the
    model; splitting them by alphabetical row order would fabricate a distinction the model never
    made (invariant #2). Consequence: a decile can be empty while another is oversized, and that is
    the honest picture rather than a bug to paper over.

    Returns a float Series (NaN where the score is missing) so the caller can group on it."""
    n_buckets = n_buckets or PARAMS["decile_count"]
    numeric = pd.to_numeric(scores, errors="coerce")
    present = numeric.dropna()
    out = pd.Series(float("nan"), index=numeric.index, dtype=float)
    if present.empty:
        return out
    # rank descending so rank 1 = highest score = decile 1
    pct = present.rank(method="average", ascending=False, pct=True)
    out.loc[present.index] = pct.apply(
        lambda p: min(n_buckets, max(1, math.ceil(p * n_buckets))))
    return out


def _daily_cross_sections(df, score_col, excess_col, min_names):
    """Yield (run_date, sub) for each day with enough scored, MATURED rows to analyse.

    Rows with non-point-in-time fundamentals are dropped first: these are composite-score metrics,
    and a stale-fundamentals row's composite is not a genuine point-in-time prediction (same rule as
    the journal's cohort grading — one shared definition, see has_stale_fundamentals)."""
    if "run_date" not in df.columns or score_col not in df.columns or excess_col not in df.columns:
        return
    clean = df[~df.apply(has_stale_fundamentals, axis=1)] if len(df) else df
    clean = clean[clean[score_col].notna() & clean[excess_col].notna()]
    for run_date, sub in clean.groupby("run_date"):
        if len(sub) >= min_names:
            yield run_date, sub


def _aggregate_daily(values):
    """Collapse a list of per-day statistics into mean / median / std / share-positive / n_days.

    Equal weight PER DAY, deliberately. Pooling every row instead would let days with more names
    dominate — and this universe grew from 58 names to 519 over the panel, so pooling would quietly
    weight 2026 several times more heavily than 2024."""
    s = pd.Series([v for v in values if v is not None and pd.notna(v)], dtype=float)
    if s.empty:
        return {"mean": None, "median": None, "std": None, "pct_positive": None, "n_days": 0}
    return {"mean": float(s.mean()), "median": float(s.median()),
            "std": float(s.std(ddof=1)) if len(s) > 1 else None,
            "pct_positive": float((s > 0).mean() * 100.0), "n_days": int(len(s))}


def _overlap_adjusted_t(mean, std, n_days, horizon):
    """t-statistic on the NON-OVERLAPPING-equivalent sample size.

    Daily snapshots with an h-day forward window overlap ~h-fold: 250 daily observations of a
    250-day return contain roughly ONE independent observation, not 250. A naive t would be ~16x
    overstated here. Effective n = n_days / horizon, floored at 1."""
    if mean is None or std in (None, 0) or not n_days or pd.isna(std):
        return None
    effective_n = max(1.0, n_days / float(horizon))
    return float(mean / (std / math.sqrt(effective_n)))


def _decile_day_stats(sub, score_col, excess_col, n_buckets):
    """{decile: mean excess} for one day. A decile with no names contributes NOTHING — it must not
    be recorded as 0.0, which would drag its cross-day average toward zero and invent an
    observation that never happened."""
    deciles = assign_deciles(sub[score_col], n_buckets)
    out = {}
    for d, grp in sub.groupby(deciles):
        if pd.notna(d):
            out[int(d)] = {"mean": float(grp[excess_col].mean()),
                           "median": float(grp[excess_col].median()),
                           "hit": float((grp[excess_col] > 0).mean() * 100.0),
                           "n": int(len(grp))}
    return out


def _selection_day_stats(sub, score_col, excess_col, n_names):
    """Stats for the top-N names on one day, plus that day's universe mean as the honest benchmark.

    ALL names tied at the cut are included rather than an arbitrary N — the model cannot distinguish
    them, so neither will this. `n` is reported truthfully, so a day where 12 names tie for slot 10
    says 12."""
    ranked = sub.assign(_r=pd.to_numeric(sub[score_col], errors="coerce")
                        .rank(method="min", ascending=False))
    picked = ranked[ranked["_r"] <= n_names]
    if picked.empty:
        return None
    return {"mean": float(picked[excess_col].mean()),
            "median": float(picked[excess_col].median()),
            "hit": float((picked[excess_col] > 0).mean() * 100.0),
            "n": int(len(picked)),
            "vs_universe": float(picked[excess_col].mean() - sub[excess_col].mean())}


def build_decile_report(df, model_version, horizons=HORIZONS):
    """Cross-sectional decile and top-N rows, ADDITIVE to the existing bucket/IC reporting.

    Why this exists: full-universe IC measures rank correlation across all ~519 names, but a human
    holds ~3. Those are different questions and the current metrics cannot separate them. Deciles
    also fix the existing buckets' imbalance — fixed 80/65/50 score bands put 31,849 names in
    `decent` and 3,627 in `strong` and drift with the regime, whereas a per-day decile always splits
    the same cross-section ten ways.

    Returns [] when `run_date` is absent, which keeps the legacy sparse-row-dict callers working."""
    if "run_date" not in df.columns:
        return []
    n_buckets = PARAMS["decile_count"]
    min_names = PARAMS["decile_min_names_per_day"]
    rows = []

    for n in horizons:
        score_col, excess_col = f"score_{n}d", f"future_excess_return_{n}d"
        per_decile = {d: [] for d in range(1, n_buckets + 1)}
        per_decile_extra = {d: {"median": [], "hit": [], "n": []} for d in range(1, n_buckets + 1)}
        spreads, sel_acc, days, degenerate = [], {k: [] for k in PARAMS["top_n_selection_sizes"]}, 0, 0

        for _run_date, sub in _daily_cross_sections(df, score_col, excess_col, min_names):
            days += 1
            if sub[score_col].nunique() <= 1:
                degenerate += 1              # every score identical: no ordering exists to measure
                continue
            stats = _decile_day_stats(sub, score_col, excess_col, n_buckets)
            for d, st in stats.items():
                per_decile[d].append(st["mean"])
                per_decile_extra[d]["median"].append(st["median"])
                per_decile_extra[d]["hit"].append(st["hit"])
                per_decile_extra[d]["n"].append(st["n"])
            if 1 in stats and n_buckets in stats:
                spreads.append(stats[1]["mean"] - stats[n_buckets]["mean"])
            for k in sel_acc:
                s = _selection_day_stats(sub, score_col, excess_col, k)
                if s:
                    sel_acc[k].append(s)

        for d in range(1, n_buckets + 1):
            agg = _aggregate_daily(per_decile[d])
            if not agg["n_days"]:
                continue
            rows.append({
                "report_type": "decile", "model_version": model_version, "horizon": f"{n}d",
                "decile": d, "n_days": agg["n_days"],
                "avg_names_per_day": round(float(pd.Series(per_decile_extra[d]["n"]).mean()), 1),
                "avg_future_excess_return": agg["mean"],
                "median_future_excess_return": float(pd.Series(per_decile_extra[d]["median"]).mean()),
                "hit_rate_pct": float(pd.Series(per_decile_extra[d]["hit"]).mean()),
                "aggregation": "equal_weight_per_day",
            })

        sp = _aggregate_daily(spreads)
        top, bot = _aggregate_daily(per_decile[1]), _aggregate_daily(per_decile[n_buckets])
        rows.append({
            "report_type": "decile_spread", "model_version": model_version, "horizon": f"{n}d",
            "n_days": sp["n_days"], "top_decile_avg_excess": top["mean"],
            "bottom_decile_avg_excess": bot["mean"], "spread_avg": sp["mean"],
            "spread_median": sp["median"], "spread_std_daily": sp["std"],
            "pct_days_spread_positive": sp["pct_positive"],
            "spread_t_stat_overlap_adj": _overlap_adjusted_t(sp["mean"], sp["std"], sp["n_days"], n),
            "decile_count": n_buckets, "min_names_per_day": min_names,
            "days_considered": days, "days_skipped_degenerate_ties": degenerate,
            "sample_adequate": bool(sp["n_days"] >= PARAMS["decile_min_days"]),
        })

        for k, entries in sel_acc.items():
            agg = _aggregate_daily([e["mean"] for e in entries])
            if not agg["n_days"]:
                continue
            rows.append({
                "report_type": "selection", "model_version": model_version, "horizon": f"{n}d",
                "selection": f"top_{k}", "n_names_target": k, "n_days": agg["n_days"],
                "avg_names_per_day": round(float(pd.Series([e["n"] for e in entries]).mean()), 1),
                "avg_future_excess_return": agg["mean"],
                "median_future_excess_return": float(pd.Series([e["median"] for e in entries]).mean()),
                "hit_rate_pct": float(pd.Series([e["hit"] for e in entries]).mean()),
                # vs the day's universe mean, not vs zero: a 3-name book in a rising tape can post a
                # positive excess return while still trailing the universe it was picked from.
                "avg_excess_vs_universe": float(pd.Series([e["vs_universe"] for e in entries]).mean()),
                "pct_days_positive": agg["pct_positive"],
                "sample_adequate": bool(agg["n_days"] >= PARAMS["decile_min_days"]),
            })
    return rows


def _recent_live_run_dates(df, window):
    """The trailing `window` distinct LIVE (non-backfilled) run_dates in df, as a set. Backfill
    rows are excluded because regime-vigilance is about how the factors behave on fresh, live
    data — the whole point is to catch a factor decaying in the present, not in the backtest.
    Returns an empty set if there are no live rows yet (the recent-IC columns then stay null and
    populate over time as live snapshots accrue)."""
    if "backfilled" not in df.columns or "run_date" not in df.columns:
        return set()
    live = df[df["backfilled"].fillna(0).astype(int) == 0]
    if live.empty:
        return set()
    distinct_dates = sorted(live["run_date"].dropna().unique())
    return set(distinct_dates[-window:])


def build_performance_review(evaluated_rows, min_sample_size=None, model_version=None,
                             recent_live_window=None):
    """evaluated_rows: list of dicts from evaluate_all_snapshots. Returns a DataFrame with
    several kinds of rows (distinguished by `report_type`): per (horizon, label) bucket stats,
    per-component Pearson/Spearman correlation against future excess return each with a descriptive
    (never auto-applied) suggested weight-change note, and — when the rows carry a `run_date` —
    per-day cross-sectional `decile` / `decile_spread` / `selection` rows.

    Every row is tagged with `model_version` so v0.1 and v0.2 can be shown side-by-side on the
    same report. Component rows also carry a RECENT spearman IC (trailing live run_dates only)
    next to the full-history IC — a materially decayed recent IC is an early regime-shift
    warning (see spec's regime-vigilance requirement)."""
    if not evaluated_rows:
        return pd.DataFrame()
    df = pd.DataFrame(evaluated_rows)
    # was a literal function default; moved to config so every tunable stays auditable (invariant #3)
    if min_sample_size is None:
        min_sample_size = PARAMS["performance_review_min_sample_size"]
    recent_live_window = recent_live_window or PARAMS["regime_recent_live_days"]
    weights_map = SCORE_WEIGHTS_BY_VERSION.get(model_version, SCORE_WEIGHTS)
    recent_dates = _recent_live_run_dates(df, recent_live_window)
    report_rows = []

    for n in HORIZONS:
        horizon_key = f"score_{n}d"
        excess_col = f"future_excess_return_{n}d"
        drawdown_col = f"max_drawdown_after_{n}d" if n in DRAWDOWN_HORIZONS else None
        if horizon_key not in df.columns or excess_col not in df.columns:
            continue
        evaluable = df[df[excess_col].notna() & df[horizon_key].notna()].copy()
        if evaluable.empty:
            continue
        evaluable["label"] = evaluable[horizon_key].apply(scoring.label_for_score)
        for label, group in evaluable.groupby("label"):
            if label is None or len(group) < 1:
                continue
            report_rows.append({
                "report_type": "bucket",
                "model_version": model_version,
                "horizon": f"{n}d",
                "label": label,
                "n": len(group),
                "avg_future_excess_return": group[excess_col].mean(),
                "median_future_excess_return": group[excess_col].median(),
                "hit_rate_pct": (group[excess_col] > 0).mean() * 100.0,
                "avg_max_drawdown_after": group[drawdown_col].mean() if drawdown_col else None,
            })

    has_recent = bool(recent_dates) and "run_date" in df.columns
    recent_df = df[df["run_date"].isin(recent_dates)] if has_recent else None

    for n in HORIZONS:
        horizon_key = f"score_{n}d"
        excess_col = f"future_excess_return_{n}d"
        if excess_col not in df.columns:
            continue
        weights_for_horizon = weights_map.get(horizon_key, {})
        for comp in _COMPONENT_COLUMNS:
            if comp not in df.columns:
                continue
            # Fundamental factors drop recovered rows (lookahead); price/volume keep every row.
            sub = _ic_base(df, comp)[[comp, excess_col]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(sub) < min_sample_size:
                continue
            pearson_ic = sub[comp].corr(sub[excess_col], method="pearson")
            spearman_ic = _spearman_ic(sub, comp, excess_col)

            # Regime-vigilance: same IC recomputed on just the trailing live run_dates.
            spearman_ic_recent, n_recent = None, 0
            if recent_df is not None and comp in recent_df.columns:
                rsub = _ic_base(recent_df, comp)[[comp, excess_col]].apply(pd.to_numeric, errors="coerce").dropna()
                n_recent = len(rsub)
                if n_recent >= min_sample_size:
                    spearman_ic_recent = _spearman_ic(rsub, comp, excess_col)

            report_rows.append({
                "report_type": "component_correlation",
                "model_version": model_version,
                "horizon": f"{n}d",
                "component": comp,
                "n": len(sub),
                "pearson_ic": pearson_ic,
                "spearman_ic": spearman_ic,
                "spearman_ic_recent": spearman_ic_recent,
                "n_recent": n_recent,
                "suggested_note": _suggested_weight_note(
                    comp, horizon_key, spearman_ic, weights_for_horizon.get(comp)
                ),
            })

    # Cross-sectional decile / top-N rows. Additive: new report_type values, and the existing `n`
    # column is deliberately left empty on them so display._component_ic_ranking (which sorts every
    # component_correlation row) cannot be polluted by rows that mean something different.
    report_rows.extend(build_decile_report(df, model_version))

    return pd.DataFrame(report_rows)


def run_evaluation(db_path=storage.DEFAULT_DB_PATH, model_version=None, output_dir=None,
                   return_rows=False, include_frozen=False):
    """Orchestrates evaluate_all_snapshots -> build_performance_review -> CSV. Safe to call
    after every run (live or backfill); writes an empty-but-valid CSV if nothing is
    evaluable yet rather than skipping the file.

    If model_version is given, only that version is evaluated. Otherwise EVERY version present
    in the DB is evaluated and the results are concatenated into one CSV, each row tagged with
    its model_version — so the report shows v0.1 next to v0.2 on the same dates (spec's
    side-by-side comparability requirement).

    return_rows=True additionally returns the concatenated evaluated rows across all versions, so
    the caller (app.main) can hand them to the journal instead of the journal recomputing the whole
    forward-return join a second (and third, per recovered day) time — one evaluation pass per run."""
    output_dir = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    versions = [model_version] if model_version else storage.list_model_versions(db_path)
    if not versions:
        versions = [PARAMS["model_version"]]

    # FROZEN versions are skipped on the nightly path. v0.1 (259k rows) and v0.4 (278k rows) were being
    # re-joined forward-return-by-forward-return from scratch every single night — a growing Python
    # loop over rows that are immutable and can never produce a new number. Their last computed report
    # rows are preserved below, so the CSV still shows them side by side; they are just not recomputed.
    # `include_frozen=True` (or naming one explicitly) forces a full recompute when that is the point.
    skipped_frozen = []
    if not model_version and not include_frozen:
        skipped_frozen = [v for v in versions if v in FROZEN_MODEL_VERSIONS]
        versions = [v for v in versions if v not in FROZEN_MODEL_VERSIONS]

    reviews, total_evaluable, all_rows = [], 0, []
    for v in versions:
        evaluated_rows = evaluate_all_snapshots(db_path, model_version=v)
        total_evaluable += len(evaluated_rows)
        all_rows.extend(evaluated_rows)
        review = build_performance_review(evaluated_rows, model_version=v)
        if not review.empty:
            reviews.append(review)

    review_df = pd.concat(reviews, ignore_index=True) if reviews else pd.DataFrame()
    review_path = os.path.join(output_dir, "performance_review.csv")

    # Carry forward the previously-computed rows for any frozen version so the report keeps showing
    # every version side by side. Dropping them would look like the older versions had stopped
    # performing rather than simply stopped being recomputed.
    if skipped_frozen and os.path.exists(review_path):
        try:
            prior = pd.read_csv(review_path)
            kept = prior[prior["model_version"].isin(skipped_frozen)]
            if not kept.empty:
                review_df = pd.concat([review_df, kept], ignore_index=True)
        except Exception as e:
            print(f"[evaluation] could not carry forward frozen-version rows ({e}) — "
                  f"they will be absent from this report, not zero")

    review_df.to_csv(review_path, index=False)
    frozen_note = f" (skipped frozen: {skipped_frozen})" if skipped_frozen else ""
    print(f"[evaluation] evaluated versions {versions}{frozen_note}: {total_evaluable} snapshot(s) "
          f"evaluable, wrote {len(review_df)} report row(s) to {review_path}")
    return (review_df, all_rows) if return_rows else review_df
