"""Clean terminal display layer — presentation only.

Reads from output/latest_rankings.csv and output/performance_review.csv (already written by
app.py's _export_csvs / evaluation.run_evaluation) and renders two clearly separated views:
today's ranked setups, and the system's historical track record. Never touches scoring.py,
evaluation.py, or storage.py, and never recomputes a number that isn't already in those CSVs.

Pure data-shaping helpers (prefixed with _) are kept separate from the rich-rendering print_*
functions so the shaping logic is testable without capturing terminal output.
"""

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src import scoring
from src.config import PARAMS

console = Console()

_LABEL_STYLES = {
    "strong": "bold green",
    "decent": "white",
    "watchlist": "white",
    "weak": "dim red",
}

# Mirrors the IC color cutoffs already encoded in evaluation._suggested_weight_note, reused
# here for consistency rather than inventing new thresholds.
_IC_STRONG_POSITIVE = 0.10
_IC_NEGATIVE = -0.05

_POSITIVE_SIGNAL_PREFIXES = (
    "relative_strength_component", "momentum_component", "medium_momentum_component",
    "long_momentum_component",
)
_SHORT_HORIZON_COMPONENTS = ("short_momentum_component", "setup_component")


def _is_missing(value):
    return value is None or (isinstance(value, float) and pd.isna(value))


def _fmt(value, decimals=1, dash="—"):
    if _is_missing(value):
        return dash
    return f"{value:.{decimals}f}"


def _ic_style(ic):
    if _is_missing(ic):
        return "dim"
    if ic > _IC_STRONG_POSITIVE:
        return "green"
    if ic < _IC_NEGATIVE:
        return "red"
    return "dim"


# ---------------------------------------------------------------------------
# View 1 — Today's Top Setups
# ---------------------------------------------------------------------------

def _build_top_setups_rows(rankings_df, watchlist_df, top_n=15):
    """Joins sector from the watchlist (display-only join, never written back), drops rows
    with no score_20d (nothing to rank), sorts descending, takes the top_n, and attaches the
    score_20d label via scoring.label_for_score — the same function evaluation.py uses, so
    the label shown here is never out of sync with the label the backtest scored against."""
    df = rankings_df.merge(watchlist_df[["ticker", "sector"]], on="ticker", how="left")
    df = df[df["score_20d"].notna()].copy()
    df = df.sort_values("score_20d", ascending=False).head(top_n).reset_index(drop=True)
    df["label_20d"] = df["score_20d"].apply(scoring.label_for_score)
    return df


def print_top_setups(latest_rankings_path, watchlist_path, top_n=15):
    rankings_df = pd.read_csv(latest_rankings_path)
    watchlist_df = pd.read_csv(watchlist_path)

    console.print(Panel(
        "[bold]Today's Top Setups[/bold] — research ranking only, NOT a buy recommendation",
        style="bold cyan",
    ))

    if rankings_df.empty:
        console.print("No rankings available yet.\n")
        return

    rows = _build_top_setups_rows(rankings_df, watchlist_df, top_n)
    run_date = rankings_df["run_date"].iloc[0]
    model_version = rankings_df["model_version"].iloc[0] if "model_version" in rankings_df.columns else "?"
    console.print(f"run_date={run_date}  model_version={model_version}  showing top {len(rows)}\n")

    if rows.empty:
        console.print("No tickers have a usable score_20d yet.\n")
        return

    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Ticker")
    table.add_column("Sector")
    table.add_column("5d", justify="right")
    table.add_column("20d", justify="right")
    table.add_column("60d", justify="right")
    table.add_column("120d", justify="right")
    table.add_column("Label")
    table.add_column("Earnings (d)", justify="right")

    for i, row in rows.iterrows():
        label = row.get("label_20d")
        style = _LABEL_STYLES.get(label, "white")
        table.add_row(
            str(i + 1),
            str(row["ticker"]),
            str(row.get("sector")) if not _is_missing(row.get("sector")) else "—",
            _fmt(row.get("score_5d")),
            _fmt(row.get("score_20d")),
            _fmt(row.get("score_60d")),
            _fmt(row.get("score_120d")),
            label.capitalize() if label else "—",
            _fmt(row.get("days_until_earnings"), decimals=0),
            style=style,
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# View 2 — System Performance Summary
# ---------------------------------------------------------------------------

def _health_check_line(review_df, horizon="20d"):
    """Plain-English check of CLAUDE.md's documented prior: momentum/relative-strength/trend
    components should carry the predictive signal; short-momentum/setup should be weak. Pure
    display-time comparison of spearman_ic values already in performance_review.csv — no new
    statistic is computed here."""
    comp_df = review_df[(review_df["report_type"] == "component_correlation") & (review_df["horizon"] == horizon)]
    if comp_df.empty:
        return f"No component correlation data yet for {horizon} — health check unavailable."

    pos_mask = (comp_df["component"].str.startswith(_POSITIVE_SIGNAL_PREFIXES)
                | (comp_df["component"] == "trend_component"))
    short_mask = comp_df["component"].isin(_SHORT_HORIZON_COMPONENTS)

    pos_ic = comp_df.loc[pos_mask, "spearman_ic"].dropna()
    short_ic = comp_df.loc[short_mask, "spearman_ic"].dropna()
    if pos_ic.empty or short_ic.empty:
        return f"Insufficient component coverage for {horizon} — health check unavailable."

    if pos_ic.mean() > short_ic.mean() and pos_ic.max() >= short_ic.max():
        return (f"Momentum/relative-strength/trend components are leading as expected on {horizon} "
                f"(avg IC {pos_ic.mean():.2f} vs short-momentum/setup avg {short_ic.mean():.2f}) "
                f"— no sign of a lookahead bug.")
    return (f"WARNING: short-momentum/setup components (avg IC {short_ic.mean():.2f}) are not clearly "
            f"weaker than momentum/relative-strength/trend (avg IC {pos_ic.mean():.2f}) on {horizon} "
            f"— possible lookahead or date-join bug, investigate before trusting scores.")


def _strong_weak_hit_rates(review_df, horizons=("5d", "20d", "60d", "120d")):
    """Pulls the two matching bucket rows (label == strong / weak) per horizon directly from
    performance_review.csv. Returns a plain DataFrame, no rendering."""
    bucket_df = review_df[review_df["report_type"] == "bucket"]
    rows = []
    for horizon in horizons:
        h = bucket_df[bucket_df["horizon"] == horizon]
        strong = h[h["label"] == "strong"]
        weak = h[h["label"] == "weak"]
        rows.append({
            "horizon": horizon,
            "strong_hit_rate_pct": strong["hit_rate_pct"].iloc[0] if not strong.empty else None,
            "strong_n": strong["n"].iloc[0] if not strong.empty else None,
            "weak_hit_rate_pct": weak["hit_rate_pct"].iloc[0] if not weak.empty else None,
            "weak_n": weak["n"].iloc[0] if not weak.empty else None,
        })
    return pd.DataFrame(rows)


def _component_ic_ranking(review_df):
    """Every component_correlation row across all horizons, sorted by spearman_ic descending."""
    comp_df = review_df[review_df["report_type"] == "component_correlation"].copy()
    return comp_df.sort_values("spearman_ic", ascending=False, na_position="last")


def _select_review_version(review_df):
    """The performance_review.csv now holds every model_version side by side. For the terminal
    summary we show ONE coherent version: the current one if it already has component IC rows,
    otherwise whichever version has the most (early after a version bump, the baseline still
    carries all the accrued history). Returns (filtered_df, version_label)."""
    if "model_version" not in review_df.columns:
        return review_df, None
    comp = review_df[review_df["report_type"] == "component_correlation"]
    current = PARAMS["model_version"]
    if not comp[comp["model_version"] == current].empty:
        chosen = current
    elif not comp.empty:
        chosen = comp["model_version"].value_counts().idxmax()
    else:
        chosen = current
    return review_df[review_df["model_version"] == chosen], chosen


def print_performance_summary(performance_review_path):
    review_df = pd.read_csv(performance_review_path)

    console.print(Panel(
        "[bold]System Performance Summary[/bold] — historical track record, NOT today's picks",
        style="bold magenta",
    ))

    if review_df.empty:
        console.print("No performance data evaluable yet.\n")
        return

    review_df, shown_version = _select_review_version(review_df)
    if review_df.empty:
        console.print("No performance data evaluable yet.\n")
        return
    if shown_version is not None:
        console.print(f"Showing model_version=[bold]{shown_version}[/bold] "
                      f"(full side-by-side detail in performance_review.csv)\n")

    console.print(_health_check_line(review_df, horizon="20d") + "\n")

    hit_rate_df = _strong_weak_hit_rates(review_df)
    hit_table = Table(title="Hit rate: Strong vs Weak buckets", show_lines=False)
    hit_table.add_column("Horizon")
    hit_table.add_column("Strong hit % (n)", justify="right")
    hit_table.add_column("Weak hit % (n)", justify="right")
    for _, row in hit_rate_df.iterrows():
        strong_cell = f"{_fmt(row['strong_hit_rate_pct'])} ({_fmt(row['strong_n'], decimals=0)})"
        weak_cell = f"{_fmt(row['weak_hit_rate_pct'])} ({_fmt(row['weak_n'], decimals=0)})"
        hit_table.add_row(row["horizon"], strong_cell, weak_cell)
    console.print(hit_table)
    console.print()

    ranked = _component_ic_ranking(review_df)
    ic_table = Table(title="Component IC ranking (strongest positive first)", show_lines=False)
    ic_table.add_column("Horizon")
    ic_table.add_column("Component")
    ic_table.add_column("n", justify="right")
    ic_table.add_column("Pearson IC", justify="right")
    ic_table.add_column("Spearman IC", justify="right")
    ic_table.add_column("Recent IC", justify="right")  # trailing live window — regime vigilance
    ic_table.add_column("Note")
    for _, row in ranked.iterrows():
        spearman = row.get("spearman_ic")
        recent = row.get("spearman_ic_recent")
        ic_table.add_row(
            str(row["horizon"]),
            str(row["component"]),
            _fmt(row.get("n"), decimals=0),
            _fmt(row.get("pearson_ic"), decimals=2),
            _fmt(spearman, decimals=2),
            _fmt(recent, decimals=2),
            str(row.get("suggested_note")) if not _is_missing(row.get("suggested_note")) else "",
            style=_ic_style(spearman),
        )
    console.print(ic_table)
    console.print()
