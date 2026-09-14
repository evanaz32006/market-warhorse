"""Daily journal — the system's durable, machine-appended memory of each run.

After every completed run (live or backfill) this writes ONE structured entry per
(run_date, model_version) and regenerates output/DAILY_LOG.md from the whole `journal` table.

Two representations, kept in lock-step:
- a JSON blob in the `journal` SQLite table (queryable history — the source of truth), and
- output/DAILY_LOG.md (the human-readable mirror, regenerated in full from the table each run).

Idempotent: re-running a run_date REPLACES that date's entry (storage.upsert_journal_entry),
never appends a duplicate. This module is a READ-ONLY consumer of existing outputs
(performance_review.csv, feature_snapshots, price_history) — it renders, it never recomputes or
mutates a scoring/evaluation VALUE. All forward-return / date-join math is reused from
evaluation.py so the no-lookahead discipline lives in exactly one place (CLAUDE.md).

Entry format is `journal_v2`: exactly four sections per day (see daily-log-redesign-spec.md) —
1) Today's Rankings, 2) Predictions that came due today, 3) Running scoreboard, 4) Live
validation tracker — plus a run-metadata preamble. Older `journal_v1` rows already in the table
are still rendered in their original format (render dispatches on the entry's `schema`).
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

from src import evaluation, scoring, storage
from src.config import ETF_SECTOR_LABEL, PARAMS

# Components whose live-only IC is the whole point of Section 4a (no backfill for these).
_V02_FACTOR_COMPONENTS = ["value_component", "quality_component", "short_interest_component"]

_TOP_N = 10
_MAX_MOVERS = 5


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_num(v):
    return isinstance(v, (int, float)) and not (isinstance(v, float) and pd.isna(v))


def _num(v):
    """Coerce a possibly-pandas/None value to a plain float, or None. Handles numpy scalars and
    NaN (isinstance(np.int64, int) is False, so _is_num alone isn't enough for CSV-sourced data)."""
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_true(flags):
    """Percentage of truthy values in a list of bools, or None for an empty list."""
    return 100.0 * sum(1 for f in flags if f) / len(flags) if flags else None


# ---------------------------------------------------------------------------
# Section builders (pure — take already-loaded data, return JSON-able dicts)
# ---------------------------------------------------------------------------

def _run_metadata_section(run_context):
    """Echoes the run's own facts (passed in by app.py — they aren't in any CSV). Rendered as a
    small preamble under the date heading (audit trail), not as one of the four sections."""
    fetch = run_context.get("fetch_summary") or {}
    return {
        "run_date": run_context.get("run_date"),
        "model_version": run_context.get("model_version"),
        "mode": ("backfill" if run_context.get("backfilled")
                 else "recovered" if run_context.get("recovered") else "live"),
        "runtime_sec": round(run_context["runtime_sec"], 1) if _is_num(run_context.get("runtime_sec")) else None,
        "tickers_scored": run_context.get("tickers_scored"),
        "fetch": {
            "fresh": len(fetch.get("fresh", [])),
            "cached_only": len(fetch.get("cached_only", [])),
            "failed": list(fetch.get("failed", [])),
        },
        "fundamentals": run_context.get("fundamentals_summary"),
        "warnings": list(run_context.get("warnings", [])),
    }


def _top_tickers(score_map, n=_TOP_N):
    """Tickers sorted by score descending, top n — a list of (ticker, score) pairs."""
    return sorted(score_map.items(), key=lambda kv: kv[1], reverse=True)[:n]


def _rankings_movement(today_scores, prev_scores, prev_run_date, exclude_from_top=frozenset()):
    """Top-10 by score_20d today, entries/exits vs the previous LIVE run, and the biggest
    single-day score movers (joined on ticker, never by row position). Tickers in
    exclude_from_top (benchmark ETFs) are dropped from the top-10 and entered/exited pools ONLY —
    movers are still computed over the full universe so a big ETF move is still visible."""
    top_pool = {t: s for t, s in today_scores.items() if t not in exclude_from_top}
    today_top = _top_tickers(top_pool)
    top_block = [{"ticker": t, "score_20d": round(s, 1)} for t, s in today_top]

    entered, exited, movers_up, movers_down = [], [], [], []
    if prev_scores:
        today_top_set = {t for t, _ in today_top}
        prev_pool = {t: s for t, s in prev_scores.items() if t not in exclude_from_top}
        prev_top_set = {t for t, _ in _top_tickers(prev_pool)}
        entered = sorted(today_top_set - prev_top_set)
        exited = sorted(prev_top_set - today_top_set)

        deltas = []
        for t, s in today_scores.items():
            if t in prev_scores:
                deltas.append((t, round(s - prev_scores[t], 1)))
        deltas.sort(key=lambda kv: kv[1], reverse=True)
        movers_up = [{"ticker": t, "delta": d} for t, d in deltas[:_MAX_MOVERS] if d > 0]
        movers_down = [{"ticker": t, "delta": d} for t, d in reversed(deltas[-_MAX_MOVERS:]) if d < 0]

    return {
        "top_10_by_score_20d": top_block,
        "compared_to_prev_live_run": prev_run_date,
        "entered_top_10": entered,
        "exited_top_10": exited,
        "biggest_gainers": movers_up,
        "biggest_losers": movers_down,
    }


def _earnings_days(row):
    """days_until_earnings for a snapshot row, or None when missing/flagged (live-only field).
    A negative value means the cached "next earnings" date is actually in the PAST (Yahoo hasn't
    published the upcoming one yet) — not a usable "earnings in N days", so treat it as unknown."""
    if row.get("earnings_date_missing"):
        return None
    d = row.get("days_until_earnings")
    if not _is_num(d) or d < 0:
        return None
    return int(d)


def _todays_rankings_section(today_rows, today_scores, prev_scores, prev_run_date, sector_map):
    """Section 1. Top-10 by score_20d for the current run (ticker/sector/score/label/earnings),
    plus entered/exited vs the previous live run and the biggest single-day movers folded in.
    Benchmark ETFs (sector == ETF_SECTOR_LABEL) are excluded from the top-10 DISPLAY only — they
    stay scored and stored in feature_snapshots, they're just not shown as research picks."""
    etfs = frozenset(t for t in today_scores if sector_map.get(t) == ETF_SECTOR_LABEL)
    movement = _rankings_movement(today_scores, prev_scores, prev_run_date, exclude_from_top=etfs)
    row_by_ticker = {r.get("ticker"): r for r in today_rows}
    top_table = []
    for item in movement["top_10_by_score_20d"]:
        t = item["ticker"]
        r = row_by_ticker.get(t, {})
        top_table.append({
            "ticker": t,
            "sector": sector_map.get(t),
            "score_20d": item["score_20d"],
            "label": scoring.label_for_score(today_scores.get(t)),
            "days_until_earnings": _earnings_days(r),
        })
    return {
        "top_10": top_table,
        "compared_to_prev_live_run": movement["compared_to_prev_live_run"],
        "entered_top_10": movement["entered_top_10"],
        "exited_top_10": movement["exited_top_10"],
        "biggest_gainers": movement["biggest_gainers"],
        "biggest_losers": movement["biggest_losers"],
    }


def _grade_cohort(rows, n):
    """Grade one (snapshot-date, horizon) cohort: bucket each row by label_for_score(score_Nd) and
    count hits (future_excess_return_Nd > 0) in the Strong and Weak buckets. Returns
    (n_evaluable, strong_hit_flags, weak_hit_flags)."""
    strong, weak, n_eval = [], [], 0
    for r in rows:
        score_n = r.get(f"score_{n}d")
        excess = r.get(f"future_excess_return_{n}d")
        if not _is_num(score_n) or not _is_num(excess):
            continue
        n_eval += 1
        label = scoring.label_for_score(score_n)
        if label == "strong":
            strong.append(excess > 0)
        elif label == "weak":
            weak.append(excess > 0)
    return n_eval, strong, weak


def _grade_all_cohorts(evaluated_rows, trading_calendar):
    """THE single source of truth for cohort grading — feeds BOTH Section 2 (today's slice) and
    Section 3 (cumulative), so the two can never disagree. A cohort is one (snapshot_date D,
    horizon N) group; for each N it matures on M = calendar[idx(D)+N] once N real sessions have
    elapsed, and is gradable iff its rows carry future_excess_return_Nd. Each cohort is tagged mode
    (live/backfill, from the `backfilled` flag — a live row's run_date is by definition a live date,
    of ANY model version, so grading never resets on a version bump; recovered rows are live). Returns
    a list of dicts: {snapshot_date, model_version, mode, horizon(int), matured_on, n, strong_hits[],
    weak_hits[]}."""
    cal_index = {d: i for i, d in enumerate(trading_calendar)}
    rows_by_key = {}
    # Recovered rows are dropped from BOTH Section 2 and Section 3 here (one filter, so the two can't
    # drift): a recovered day's composite score has stale fundamentals baked in, so it isn't a genuine
    # point-in-time prediction and must not be graded as one. Same is_recovered rule 4a uses. Recovered
    # days still score/store/show in Section 1 and journal as `recovered` — only the validation buckets
    # exclude them.
    for r in evaluation.exclude_recovered(evaluated_rows):
        mode = "backfill" if int(r.get("backfilled") or 0) else "live"
        # Key on version too, so two model versions sharing a run_date are graded as separate cohorts.
        rows_by_key.setdefault((r.get("run_date"), r.get("model_version"), mode), []).append(r)

    cohorts = []
    for (d, version, mode), rows in rows_by_key.items():
        idx_d = cal_index.get(d)
        for n in evaluation.HORIZONS:
            n_eval, strong, weak = _grade_cohort(rows, n)
            if n_eval == 0:
                continue  # not matured / not gradable at this horizon yet
            matured_on = (trading_calendar[idx_d + n]
                          if idx_d is not None and idx_d + n < len(trading_calendar) else None)
            cohorts.append({
                "snapshot_date": d, "model_version": version, "mode": mode,
                "horizon": n, "matured_on": matured_on, "n": n_eval,
                "strong_hits": strong, "weak_hits": weak,
            })
    return cohorts


def _matured_cohorts_section(cohorts, run_date, mode="live"):
    """Section 2. The cohorts of one MODE that matured EXACTLY today (matured_on == run_date), taken
    from the shared grader — so every name counted here is also counted in Section 3. A cohort is
    graded once, in the entry for its maturity day, labelled by its model version.

    `mode` selects live (real-time predictions) or backfill (the same model reconstructed
    point-in-time over history). Both are graded by identical logic; only the row source differs."""
    low_conf_n = PARAMS["cohort_low_confidence_min_n"]
    min_bucket_n = PARAMS["scoreboard_min_bucket_n"]
    out = []
    for c in cohorts:
        if c["mode"] != mode or c["matured_on"] != run_date:
            continue
        strong_n, weak_n = len(c["strong_hits"]), len(c["weak_hits"])
        # Gate each bucket's hit rate on its OWN n, not the cohort total — a "Strong 0.0% (n=2)" is
        # noise dressed as a finding. Same threshold Section 3 gates its cells at, so the two sections
        # treat small buckets identically; _fmt_hit renders a None pct as "n/a (n=X)".
        sh = _pct_true(c["strong_hits"]) if strong_n >= min_bucket_n else None
        wh = _pct_true(c["weak_hits"]) if weak_n >= min_bucket_n else None
        out.append({
            "snapshot_date": c["snapshot_date"],
            "model_version": c["model_version"],
            "horizon": f"{c['horizon']}d",
            "n": c["n"],
            "strong_hit_pct": round(sh, 1) if sh is not None else None,
            "strong_n": strong_n,
            "weak_hit_pct": round(wh, 1) if wh is not None else None,
            "weak_n": weak_n,
            # The middle bands are not graded, but their COUNT is reported. Printing only the two
            # extremes made the line read as broken arithmetic - "6 strong vs 287 weak" out of 515
            # leaves 222 names unaccounted for, with nothing saying they exist.
            "middle_n": c["n"] - strong_n - weak_n,
            # The spread is the actual claim being tested; leaving the reader to subtract two
            # percentages buries it.
            "spread_pts": (round(sh - wh, 1) if (sh is not None and wh is not None) else None),
            "low_confidence": c["n"] < low_conf_n,
        })
    out.sort(key=lambda x: (x["horizon"], x["snapshot_date"]))
    return {"cohorts": out}


def _matured_cohorts_dual(cohorts, run_date, current_version):
    """Section 2 as TWO counters for the SAME model: live and simulated.

    `live` is what the bot actually predicted in real time. It is empty for weeks after a model
    promotion, because the new version has no matured cohorts yet.

    `simulated` is the same model's BACKFILLED predictions - this exact algorithm, these exact
    weights, applied point-in-time to an earlier date. A backfilled snapshot from 120 sessions ago
    matures today, so it answers the question the live counter cannot yet: how is THIS model doing in
    the market that is happening right now, rather than in a two-year average.

    That is the measurement worth watching. A regime turns over long before a live track record can
    accumulate, so waiting 120 trading days for the first live 120d cohort means learning how the
    model performed in a regime that has already ended.

    The two are labelled and kept apart, never merged: a simulated cohort is a reconstruction (no
    slippage, no missed fill, and it knows the universe as it is constituted today), so it is
    evidence of a different weight than a real-time prediction. Earlier MODEL VERSIONS answer a
    different question and are deliberately not shown here."""
    live = _matured_cohorts_section(cohorts, run_date)["cohorts"]
    sim = _matured_cohorts_section(cohorts, run_date, mode="backfill")["cohorts"]
    return {
        "cohorts": live,                      # back-compat: existing renderer/tests read this
        "model_version": current_version,
        "live": {"cohorts": live},
        "simulated": {"cohorts": sim},
    }


def _running_scoreboard_section(cohorts, evaluated_rows, run_date):
    """Section 3. Cumulative Strong-vs-Weak hit rate per horizon, split live vs backfill — aggregated
    from the SAME cohorts Section 2 grades, so Section 3 == Σ(Section 2 over all days) BY CONSTRUCTION
    and the two are incapable of drifting. Only cohorts matured BY run_date are counted, so a
    re-journaled past day reflects its own as-of state, not the present. The backfill-baseline caption
    is descriptive (all backfill rows, from evaluated_rows)."""
    min_n = PARAMS["scoreboard_min_bucket_n"]
    acc = {}  # (mode, n, bucket) -> [total, hits]
    for c in cohorts:
        if c["matured_on"] is None or c["matured_on"] > run_date:
            continue  # not yet matured as of this entry's date
        for bucket, hits in (("strong", c["strong_hits"]), ("weak", c["weak_hits"])):
            tot, hit = acc.get((c["mode"], c["horizon"], bucket), (0, 0))
            acc[(c["mode"], c["horizon"], bucket)] = (tot + len(hits),
                                                      hit + sum(1 for h in hits if h))

    def _cell(mode, n, bucket):
        tot, hit = acc.get((mode, n, bucket), (0, 0))
        pct = round(100.0 * hit / tot, 1) if tot >= min_n else None
        return {"hit_pct": pct, "n": tot}

    out = {"live": {}, "backfill": {}}
    for mode in ("live", "backfill"):
        for n in evaluation.HORIZONS:
            out[mode][f"{n}d"] = {"strong": _cell(mode, n, "strong"), "weak": _cell(mode, n, "weak")}

    # Backfill-baseline caption: dominant backfill version + its session span (all backfill rows, not
    # gated on run_date — a descriptive label for the comparison column).
    bf_rows, bf_dates = {}, {}
    for r in evaluated_rows:
        if int(r.get("backfilled") or 0):
            v = r.get("model_version")
            bf_rows[v] = bf_rows.get(v, 0) + 1
            bf_dates.setdefault(v, set()).add(r.get("run_date"))
    if bf_rows:
        bv = max(bf_rows, key=bf_rows.get)
        ds = sorted(d for d in bf_dates[bv] if d)
        out["backfill_baseline"] = {"version": bv, "sessions": len(ds),
                                    "start": ds[0] if ds else None, "end": ds[-1] if ds else None}
    return out


def _running_scoreboard_dual(cohorts, evaluated_rows, run_date, current_version):
    """Section 3 already reports live and backfill side by side; this only labels the model version
    those numbers belong to."""
    out = _running_scoreboard_section(cohorts, evaluated_rows, run_date)
    out["model_version"] = current_version
    return out


def _factor_ic_map(comps, factor_min_n):
    """{component: {horizon: {ic, n}} or None} from component_correlation rows.

    Shared by both 4a readings so the full-panel and live-only numbers are computed by identical
    logic and can differ only in which rows they were built from."""
    out = {}
    for comp in _V02_FACTOR_COMPONENTS:
        by_h = {}
        rows = comps[comps["component"] == comp]
        for _, r in rows.iterrows():
            n = r.get("n")
            ic = r.get("spearman_ic")
            if n is None or not _is_num(n) or int(n) < factor_min_n or not _is_num(ic):
                continue
            by_h[r.get("horizon")] = {"ic": round(float(ic), 3), "n": int(n)}
        out[comp] = by_h or None
    return out


def _live_validation_section(review_df, model_version, live_run_dates, live_review_df=None):
    """Section 4. Two distinct jobs kept separate:
    4a — IC of the value/quality/short-interest factors, reported TWICE: over the full panel and over
         LIVE rows only. Below the meaningfulness threshold it says "too early (n=X)" rather than
         printing a misleading number.
    4b — recent-window vs full-history IC drift on the ESTABLISHED components (everything else);
         flag |recent - full| >= threshold once the recent window is populated, else "too early".

    Why 4a needs both numbers rather than one. This section used to assume "these components have no
    backfill, so full IC == live IC", which held for v0.2/v0.3 because yfinance could not reconstruct
    fundamentals historically. v0.4 made them backfillable from EDGAR filings and the assumption
    silently stopped being true: under v0.5 the section captioned "live IC" was reporting n=750,239
    against 4 live trading days.

    The two answer different questions and both are worth seeing. FULL-PANEL is the large-sample
    estimate, but it is dominated by the backfill the weights were selected on, so it is in-sample-ish
    and flattering. LIVE-ONLY is the genuine out-of-sample read - which is what 4a exists for - and it
    is small and slow to accrue, especially right after a version promotion."""
    factor_min_n = PARAMS["factor_ic_min_n"]
    drift_threshold = PARAMS["ic_drift_flag_threshold"]
    section = {
        "model_version": model_version,
        "live_trading_days_accumulated": len(live_run_dates),
        "first_live_run_date": live_run_dates[0] if live_run_dates else None,
        "latest_live_run_date": live_run_dates[-1] if live_run_dates else None,
        "recent_window": PARAMS["regime_recent_live_days"],  # live days needed before 4b computes
        "new_factor_ic": {c: None for c in _V02_FACTOR_COMPONENTS},        # 4a full-panel
        "new_factor_ic_live": {c: None for c in _V02_FACTOR_COMPONENTS},   # 4a live-only
        "drift": [],                                                       # 4b
    }

    comps = None
    if review_df is not None and not review_df.empty and "model_version" in review_df.columns:
        comps = review_df[(review_df["model_version"] == model_version)
                          & (review_df["report_type"] == "component_correlation")]
        if comps.empty:
            comps = None

    if comps is None:
        return section

    # 4a (live-only). Computed from a review built over LIVE rows alone, so it is a genuine
    # out-of-sample read rather than the backfill the weights were chosen on.
    if live_review_df is not None and not live_review_df.empty:
        live_comps = live_review_df[
            (live_review_df["model_version"] == model_version)
            & (live_review_df["report_type"] == "component_correlation")]
        if not live_comps.empty:
            section["new_factor_ic_live"] = _factor_ic_map(live_comps, factor_min_n)

    # 4a (full panel). Large sample, but dominated by backfilled rows -> flattering, not out-of-sample.
    for comp in _V02_FACTOR_COMPONENTS:
        by_h = {}
        for _, row in comps[comps["component"] == comp].iterrows():
            ic, n = _num(row.get("spearman_ic")), _num(row.get("n"))
            if ic is None or n is None:
                continue
            by_h[row.get("horizon")] = {
                "ic": round(ic, 3),
                "n": int(n),
                "too_early": int(n) < factor_min_n,
            }
        section["new_factor_ic"][comp] = by_h or None

    # 4b — drift on established components (everything that is NOT a v0.2 factor).
    for _, row in comps.iterrows():
        comp = row.get("component")
        if comp in _V02_FACTOR_COMPONENTS:
            continue
        full = _num(row.get("spearman_ic"))
        recent = _num(row.get("spearman_ic_recent"))
        n_recent = _num(row.get("n_recent"))
        too_early = recent is None  # evaluation only fills recent IC once its window has enough rows
        drift_flag = (not too_early and full is not None
                      and abs(recent - full) >= drift_threshold)
        section["drift"].append({
            "component": comp,
            "horizon": row.get("horizon"),
            "ic_full": round(full, 3) if full is not None else None,
            "ic_recent": round(recent, 3) if recent is not None else None,
            "n_recent": int(n_recent) if n_recent is not None else 0,
            "too_early": too_early,
            "drift_flag": bool(drift_flag),
        })
    return section


# ---------------------------------------------------------------------------
# Entry assembly
# ---------------------------------------------------------------------------

def build_journal_entry(run_context, review_df, today_rows, prev_scores, prev_run_date,
                        live_run_dates, evaluated_rows, trading_calendar, sector_map):
    """Assemble the full journal_v2 entry dict from already-loaded inputs. Pure and deterministic
    so a synthetic run is fully testable without a DB or network.

    Sections 2 and 3 are both derived from ONE shared cohort grader (_grade_all_cohorts), so the
    per-day matured cohorts (Section 2) and the cumulative scoreboard (Section 3) are the same numbers
    viewed two ways and cannot drift. live_run_dates is the CURRENT version's live dates (Sections 1
    & 4); Section 2/3 span every version via each row's own backfilled flag + model_version."""
    model_version = run_context.get("model_version")
    run_date = run_context.get("run_date")
    today_scores = {r.get("ticker"): r.get("score_20d")
                    for r in today_rows if _is_num(r.get("score_20d"))}
    # Filter to the CURRENT version first. evaluated_rows has historically spanned every version
    # (each row carries its own model_version), so grading it wholesale would put an older version's
    # cohorts under the current model's heading.
    cur_rows = [r for r in evaluated_rows if r.get("model_version") == model_version]
    # A LIVE-ONLY review for Section 4a, built with evaluation.build_performance_review so the
    # live and full-panel ICs come out of identical aggregation logic rather than a parallel one.
    live_rows = [r for r in cur_rows if not int(r.get("backfilled") or 0)]
    live_review_df = (evaluation.build_performance_review(live_rows, model_version=model_version)
                      if live_rows else None)
    cohorts = _grade_all_cohorts(cur_rows, trading_calendar)
    return {
        "schema": "journal_v2",
        "generated_at": _now_iso(),
        "run": _run_metadata_section(run_context),
        "todays_rankings": _todays_rankings_section(
            today_rows, today_scores, prev_scores, prev_run_date, sector_map),
        "matured_cohorts": _matured_cohorts_dual(cohorts, run_date, model_version),
        "running_scoreboard": _running_scoreboard_dual(cohorts, evaluated_rows, run_date,
                                                       model_version),
        "live_validation": _live_validation_section(review_df, model_version, live_run_dates,
                                                    live_review_df=live_review_df),
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt_ic(v):
    return f"{v:+.3f}" if _is_num(v) else "—"


def _fmt_hit(pct, n, min_n=None):
    """A bucket's hit rate, or WHY there isn't one.

    "n/a (n=6)" read like a bug to the owner, and fairly: it prints a count next to "not available"
    without saying that the count IS the reason. A suppressed hit rate is a deliberate refusal - six
    names is far too few for a percentage to mean anything - so the rendering now says that out
    loud instead of leaving the reader to infer it."""
    if pct is not None:
        return f"{pct}% (n={n})"
    min_n = min_n if min_n is not None else PARAMS["scoreboard_min_bucket_n"]
    if n == 0:
        return "no names in this bucket"
    return f"only {n} name{'s' if n != 1 else ''}, too few to score (needs {min_n})"


def _render_entry_v2(entry, brief=None):
    """Render a journal_v2 entry (four sections + run-metadata preamble + optional brief)."""
    run = entry.get("run", {})
    mv = run.get("model_version", "?")
    lines = [f"## {run.get('run_date', '?')} — {mv} ({run.get('mode', '?')})", ""]

    if brief:
        lines += ["**Brief:**", "", brief.strip(), ""]

    # Run-metadata preamble (audit trail, not a numbered section)
    fetch = run.get("fetch", {})
    failed = fetch.get("failed", [])
    runtime = run.get("runtime_sec")
    # A re-journaled past date has no live runtime or ticker count - those belong to the run that
    # already finished. Rendering "scored None tickers in unknown time" makes a routine regeneration
    # look like a broken run, so the absent case says what it actually is.
    n_scored = run.get("tickers_scored")
    if n_scored is None and runtime is None:
        # early-return would skip every section below it; append and fall through instead
        lines.append("_Run: regenerated from stored snapshots "
                     "(original run metrics not recorded)._")
        lines.append("")
        meta = None
    else:
        runtime_str = f"{runtime}s" if runtime is not None else "unknown time"
        meta = (f"_Run: scored {n_scored if n_scored is not None else '?'} tickers in {runtime_str} · "
                f"fetch fresh={fetch.get('fresh', 0)} / cached={fetch.get('cached_only', 0)} / "
                f"failed={len(failed)}"
                + (f" ({', '.join(failed[:10])}{'…' if len(failed) > 10 else ''})" if failed else "")
                + "_")
    if meta:
        lines.append(meta)
    fund = run.get("fundamentals")
    if fund:
        lines.append(f"_Fundamentals: {fund}_")
    warnings = run.get("warnings", [])
    if warnings:
        lines.append("_Warnings: " + "; ".join(str(w) for w in warnings[:10]) + "_")
    lines.append("")

    lines += _render_section1(entry.get("todays_rankings", {}))
    lines += _render_section2(entry.get("matured_cohorts", {}))
    lines += _render_section3(entry.get("running_scoreboard", {}))
    lines += _render_section4(entry.get("live_validation", {}))

    lines += ["---", ""]
    return "\n".join(lines)


def _render_section1(sec):
    lines = ["### 1. Today's Rankings", "",
             "_Research ranking, NOT a buy recommendation._", ""]
    top = sec.get("top_10", [])
    if top:
        lines += ["| # | Ticker | Sector | score_20d | Label | Earnings in |",
                  "|---|--------|--------|-----------|-------|-------------|"]
        for i, r in enumerate(top, start=1):
            earn = r.get("days_until_earnings")
            earn_str = f"{earn}d" if earn is not None else "—"
            lines.append(f"| {i} | {r['ticker']} | {r.get('sector') or '—'} | "
                         f"{r.get('score_20d')} | {r.get('label') or '—'} | {earn_str} |")
    else:
        lines.append("_No ranked names for this run._")

    if sec.get("compared_to_prev_live_run"):
        entered = sec.get("entered_top_10", [])
        exited = sec.get("exited_top_10", [])
        lines.append("")
        lines.append(f"**vs prev live run ({sec['compared_to_prev_live_run']}):** "
                     f"entered [{', '.join(entered) or '—'}] · exited [{', '.join(exited) or '—'}]")
        gain, loss = sec.get("biggest_gainers", []), sec.get("biggest_losers", [])
        if gain or loss:
            lines.append("**Movers:** ↑ "
                         + (", ".join(f"{g['ticker']} {g['delta']:+}" for g in gain) or "—")
                         + "  ↓ "
                         + (", ".join(f"{l['ticker']} {l['delta']:+}" for l in loss) or "—"))
    else:
        lines.append("")
        lines.append("**vs prev live run:** none yet (first live run for this version)")
    lines.append("")
    return lines


def _render_cohort_lines(cohorts):
    out = []
    for c in cohorts:
        flag = "  _(low confidence)_" if c.get("low_confidence") else ""
        strong = _fmt_hit(c.get("strong_hit_pct"), c.get("strong_n", 0))
        weak = _fmt_hit(c.get("weak_hit_pct"), c.get("weak_n", 0))
        ver = c.get("model_version")
        ver_str = f" \u00b7 {ver}" if ver else ""
        spread = (f" **Spread: {c['spread_pts']:+.1f} pts.**"
                  if c.get("spread_pts") is not None else "")
        mid = c.get("middle_n")
        mid_str = f" ({mid} mid-ranked, not graded)" if mid else ""
        out.append(
            f"- Scored **{c['snapshot_date']}**{ver_str}, graded **{c['horizon']}** later"
            f" — {c['n']} stocks{mid_str}. "
            f"Top-rated: {strong}. Bottom-rated: {weak}.{spread}{flag}")
    return out


def _render_section2(sec):
    """Two counters, deliberately not merged.

    A model promotion resets the live record to zero, so the current-version counter reads empty for
    weeks while the new version's first cohorts mature. The all-versions counter preserves the track
    record across that boundary. They are shown side by side rather than combined because a score of
    80 means "top of ~1,500 peers" under one version and "top of ~500" under another - real
    continuity, but not an identical measurement."""
    lines = ["### 2. Predictions that came due today", ""]
    ver = sec.get("model_version")
    live = (sec.get("live") or {}).get("cohorts", sec.get("cohorts", []))
    sim = (sec.get("simulated") or {}).get("cohorts", [])

    lines.append(f"**Live predictions**{f' ({ver})' if ver else ''}")
    lines.append("")
    lines += _render_cohort_lines(live) or ["_None matured today._"]
    lines.append("")

    if sim:
        lines.append("**Simulated \u2014 same model, backfilled over history**")
        lines.append("")
        lines += _render_cohort_lines(sim)
        lines.append("")
        lines.append("_Simulated cohorts are this exact model scored point-in-time on an earlier "
                     "date, so they show how it is performing in the CURRENT market regime rather "
                     "than waiting for a live track record to accrue. They are reconstructions: no "
                     "slippage, no missed fills, and the universe is as constituted today._")
        lines.append("")
    return lines


def _render_section3(sec):
    lines = ["### 3. Running scoreboard — cumulative Strong vs Weak hit rate", "",
             "| Horizon | Live Strong | Live Weak | Backfill Strong | Backfill Weak |",
             "|---------|-------------|-----------|-----------------|---------------|"]
    live, backfill = sec.get("live", {}), sec.get("backfill", {})
    for n in evaluation.HORIZONS:
        h = f"{n}d"
        lv, bf = live.get(h, {}), backfill.get(h, {})

        def _c(cells, bucket):
            cell = cells.get(bucket, {})
            return _fmt_hit(cell.get("hit_pct"), cell.get("n", 0))

        lines.append(f"| {h} | {_c(lv, 'strong')} | {_c(lv, 'weak')} | "
                     f"{_c(bf, 'strong')} | {_c(bf, 'weak')} |")
    baseline = sec.get("backfill_baseline")
    if baseline and baseline.get("version"):
        span = (f", {baseline['start']} → {baseline['end']}"
                if baseline.get("start") and baseline.get("end") else "")
        lines.append("")
        lines.append(f"_Backfill baseline: {baseline['version']} "
                     f"({baseline.get('sessions', 0)} sessions{span})._")
        lines.append("_Backfill is survivorship-flattered: today's S&P constituents, "
                     "delisted names absent — read the backfill columns as optimistic._")
    lines.append("")
    return lines


def _render_section4(sec):
    lines = ["### 4. Live validation tracker", ""]
    days = sec.get("live_trading_days_accumulated", 0)
    first = sec.get("first_live_run_date")
    since = f" since {first}" if first else ""
    lines.append("**4a. Fundamental-factor IC** \u2014 do value/quality earn their weight?")
    lines.append("")

    def _factor_lines(ic_map, empty_msg):
        out = []
        for comp in _V02_FACTOR_COMPONENTS:
            by_h = (ic_map or {}).get(comp)
            if not by_h:
                out.append(f"  - {comp}: {empty_msg}")
                continue
            parts = []
            for h, d in by_h.items():
                if d.get("too_early"):
                    parts.append(f"{h} too early (n={d.get('n')})")
                else:
                    parts.append(f"{h} {_fmt_ic(d.get('ic'))} (n={d.get('n')})")
            out.append(f"  - {comp}: " + ", ".join(parts))
        return out

    lines.append(f"_Live only \u2014 {days} live trading day(s){since}. The genuine out-of-sample "
                 f"read, and the one 4a exists for._")
    lines += _factor_lines(sec.get("new_factor_ic_live"), "too early (no live IC yet)")
    lines.append("")
    lines.append("_Full panel \u2014 includes backfilled rows. Large sample, but the weights were "
                 "chosen on this data, so treat it as in-sample and flattering._")
    lines += _factor_lines(sec.get("new_factor_ic"), "no IC yet")
    lines.append("")

    lines.append("**4b. Drift on established components** (recent-window IC vs full history)")
    drift = sec.get("drift", [])
    computed = [d for d in drift if not d.get("too_early")]
    flagged = [d for d in computed if d.get("drift_flag")]
    if not computed:
        window = sec.get("recent_window")
        prog = f" ({days}/{window} live days)" if window else ""
        lines.append(f"  - too early — accruing{prog}")
    elif not flagged:
        lines.append(f"  - no material drift ({len(computed)} component-horizon(s) in range)")
    else:
        for d in flagged:
            lines.append(f"  - **DRIFT** {d['component']}@{d['horizon']}: "
                         f"{_fmt_ic(d.get('ic_full'))} → {_fmt_ic(d.get('ic_recent'))} "
                         f"(recent n={d.get('n_recent')})")
    lines.append("")
    return lines


# --- Legacy journal_v1 renderer (for entries written before the redesign) --------------------

def _render_entry_v1(entry, brief=None):
    """Render a pre-redesign journal_v1 entry in its ORIGINAL format, so regenerating DAILY_LOG.md
    never rewrites history. New entries are journal_v2 and use _render_entry_v2."""
    run = entry.get("run", {})
    mv = run.get("model_version", "?")
    lines = [f"## {run.get('run_date', '?')} — {mv} ({run.get('mode', '?')})", ""]

    if brief:
        lines += ["**Brief:**", "", brief.strip(), ""]

    fetch = run.get("fetch", {})
    failed = fetch.get("failed", [])
    runtime = run.get("runtime_sec")
    runtime_str = f"{runtime}s" if runtime is not None else "unknown time"
    lines += [
        "**Run:** "
        f"scored {run.get('tickers_scored', '?')} tickers in {runtime_str} · "
        f"fetch fresh={fetch.get('fresh', 0)} / cached={fetch.get('cached_only', 0)} / "
        f"failed={len(failed)}"
        + (f" ({', '.join(failed[:10])}{'…' if len(failed) > 10 else ''})" if failed else ""),
    ]
    fund = run.get("fundamentals")
    if fund:
        lines.append(f"**Fundamentals:** {fund}")
    warnings = run.get("warnings", [])
    if warnings:
        lines.append("**Warnings:** " + "; ".join(str(w) for w in warnings[:10]))
    lines.append("")

    mv_sec = entry.get("rankings_movement", {})
    top = mv_sec.get("top_10_by_score_20d", [])
    if top:
        lines.append("**Top 10 (score_20d):** "
                     + ", ".join(f"{r['ticker']} {r['score_20d']}" for r in top))
    entered, exited = mv_sec.get("entered_top_10", []), mv_sec.get("exited_top_10", [])
    if mv_sec.get("compared_to_prev_live_run"):
        lines.append(f"**vs prev live run ({mv_sec['compared_to_prev_live_run']}):** "
                     f"entered [{', '.join(entered) or '—'}] · exited [{', '.join(exited) or '—'}]")
        gain = mv_sec.get("biggest_gainers", [])
        loss = mv_sec.get("biggest_losers", [])
        if gain or loss:
            lines.append("**Movers:** ↑ "
                         + (", ".join(f"{g['ticker']} {g['delta']:+}" for g in gain) or "—")
                         + "  ↓ "
                         + (", ".join(f"{l['ticker']} {l['delta']:+}" for l in loss) or "—"))
    else:
        lines.append("**vs prev live run:** none yet (first live run for this version)")
    lines.append("")

    ev = entry.get("evaluation_state")
    if ev and ev.get("horizons"):
        lines.append("**Evaluation state (hit rate Strong / Weak):**")
        for h, s in ev["horizons"].items():
            sh = s.get("strong_hit_pct")
            wh = s.get("weak_hit_pct")
            lines.append(f"  - {h}: "
                         f"{sh if sh is not None else '—'}% / {wh if wh is not None else '—'}% "
                         f"(n≈{s.get('evaluable_snapshots', '—')})")
        drifting = [d for d in ev.get("component_ic_drift", []) if d.get("drift_flag")]
        if drifting:
            lines.append("  - IC drift flags (recent vs full): "
                         + "; ".join(f"{d['component']}@{d['horizon']} "
                                     f"{_fmt_ic(d['ic_full'])}→{_fmt_ic(d['ic_recent'])}"
                                     for d in drifting))
    else:
        lines.append("**Evaluation state:** no evaluable snapshots for this version yet.")
    lines.append("")

    v = entry.get("v02_live_validation", {})
    lines.append(f"**v0.2 live-validation:** {v.get('live_trading_days_accumulated', 0)} live "
                 f"trading day(s) accrued.")
    factor_ic = v.get("factor_ic_live_only", {})
    any_ic = any(factor_ic.get(c) for c in _V02_FACTOR_COMPONENTS)
    if any_ic:
        for comp in _V02_FACTOR_COMPONENTS:
            by_h = factor_ic.get(comp)
            if by_h:
                lines.append(f"  - {comp}: "
                             + ", ".join(f"{h} {_fmt_ic(ic)}" for h, ic in by_h.items()))
    else:
        lines.append("  - value/quality/short-interest IC: pending "
                     "(needs forward returns to elapse on live data).")
    lines += ["", "---", ""]
    return "\n".join(lines)


def render_entry_markdown(entry, brief=None):
    """Render one structured entry to Markdown, dispatching on its schema so old journal_v1
    entries keep their original format and new journal_v2 entries use the four-section layout."""
    if entry.get("schema") == "journal_v2":
        return _render_entry_v2(entry, brief=brief)
    return _render_entry_v1(entry, brief=brief)


def render_daily_log(journal_rows):
    """Regenerate the whole DAILY_LOG.md from every journal row (newest first). Rebuilding from
    the table each run is what makes the file idempotent — no fragile in-place editing."""
    header = [
        "# market-warhorse — Daily Log",
        "",
        "_Machine-appended after every run. Regenerated from the `journal` table; do not edit "
        "by hand. Newest entry first._",
        "",
        "---",
        "",
    ]
    body = []
    for row in journal_rows:
        try:
            entry = json.loads(row["entry_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        body.append(render_entry_markdown(entry, brief=row.get("brief")))
    return "\n".join(header + body) + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _load_review_df(output_dir):
    path = os.path.join(output_dir, "performance_review.csv")
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        return df if not df.empty else None
    except (pd.errors.EmptyDataError, OSError):
        return None


def _sector_map_from_watchlist(path=None):
    """{ticker: sector} read from watchlist.csv. Fail-soft: an unreadable watchlist returns {} rather
    than raising, because the journal must never break a completed run."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.csv")
    try:
        wl = pd.read_csv(path)
        return dict(zip(wl["ticker"], wl["sector"]))
    except Exception as e:
        print(f"[journal] could not read watchlist for sector labels ({e}) - "
              f"sectors will render blank and ETFs will not be filtered from the top-10")
        return {}


def _trading_calendar(db_path):
    """The master NYSE session calendar, delegated to evaluation.trading_calendar.

    This used to be a second implementation with "SPY" hardcoded, while evaluation's read
    PARAMS["calendar_ticker"]. Two calendars that can disagree about which day is D+20 is exactly how
    a maturity bug gets in - one module grading a cohort the other thinks is not ripe - and the
    hardcoded ticker also violated the all-tunables-in-config rule."""
    return evaluation.trading_calendar(db_path=db_path)


def run_journal(run_context, db_path=storage.DEFAULT_DB_PATH, output_dir=None, evaluated_rows=None):
    """Load the read-only inputs, build the entry, upsert it (idempotent), and regenerate
    DAILY_LOG.md from the whole table. Returns the entry dict (so brief.py can summarize it).
    Never raises out of a normal run — the journal must not break the pipeline.

    evaluated_rows (all versions, forward-returns joined) may be injected by app.main so the whole
    forward-return evaluation runs ONCE per run instead of again here (and once per recovered day);
    when None, it's computed locally so standalone/test callers still work."""
    output_dir = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    model_version = run_context.get("model_version") or PARAMS["model_version"]
    run_date = run_context.get("run_date")
    review_df = _load_review_df(output_dir)

    # Section 1 inputs: today's snapshot rows (scores + earnings, no price history needed) and the
    # previous LIVE run's scores for movement (joined on ticker, never by row position).
    today_rows = storage.load_snapshots_for_date(model_version, run_date, db_path=db_path)
    live_dates = storage.get_live_run_dates(model_version, db_path=db_path)
    prev_live, prev_scores = None, {}
    if not run_context.get("backfilled"):
        earlier = [d for d in live_dates if d < run_date]
        if earlier:
            prev_live = earlier[-1]
            prev_scores = storage.get_score_map(model_version, prev_live, db_path=db_path)

    # Sections 2 & 3 span ALL model versions: a cohort's grade (Section 2) and the backfill
    # baseline (Section 3) must not reset when the model version bumps. Every evaluated row carries
    # its own model_version + backfilled flag, so the section builders split/label by them. Each
    # snapshot is joined forward by real trading date (the no-lookahead engine).
    if evaluated_rows is None:
        # Only the CURRENT version here - prior versions are supplied by the live-only loader above,
        # which is far cheaper (live rows are ~23k across all versions; backfilled rows are ~1.3M).
        evaluated_rows = evaluation.evaluate_all_snapshots(db_path, model_version=model_version)
    trading_calendar = _trading_calendar(db_path)
    # Derive from the watchlist when the caller did not supply one. An EMPTY sector_map degrades
    # silently and badly: sectors render as "-" and, worse, the benchmark-ETF exclusion is computed
    # FROM this map, so XLV/XLE/XLB start appearing as the top-ranked research picks. Plausible-looking
    # wrong output is the failure mode this project keeps getting bitten by, so the journal now sources
    # its own map rather than trusting every caller to remember.
    sector_map = run_context.get("sector_map") or _sector_map_from_watchlist()

    entry = build_journal_entry(run_context, review_df, today_rows, prev_scores, prev_live,
                                live_dates, evaluated_rows, trading_calendar, sector_map)

    storage.upsert_journal_entry(
        run_date, model_version, bool(run_context.get("backfilled")),
        json.dumps(entry), _now_iso(), db_path=db_path,
    )
    log_path = os.path.join(output_dir, "DAILY_LOG.md")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(render_daily_log(storage.load_all_journal_entries(db_path)))

    print(f"[journal] wrote entry for {run_date} ({model_version}) and regenerated {log_path}")
    return entry
