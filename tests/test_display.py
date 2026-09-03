"""Proof tests for the display layer's pure data-shaping functions (no rich/console
dependency, no DB/network) — top-N selection, sector join, label attachment, the health-check
comparison, and the strong-vs-weak hit-rate extraction.
"""

import numpy as np
import pandas as pd

from src import display


def _rankings_df():
    return pd.DataFrame([
        {"ticker": "AAA", "run_date": "2026-06-26", "model_version": "v0.1_price_volume_only",
         "score_5d": 10.0, "score_20d": 90.0, "score_60d": 80.0, "score_120d": 70.0,
         "days_until_earnings": 3.0},
        {"ticker": "BBB", "run_date": "2026-06-26", "model_version": "v0.1_price_volume_only",
         "score_5d": 20.0, "score_20d": 70.0, "score_60d": 60.0, "score_120d": 50.0,
         "days_until_earnings": np.nan},
        {"ticker": "CCC", "run_date": "2026-06-26", "model_version": "v0.1_price_volume_only",
         "score_5d": 30.0, "score_20d": 40.0, "score_60d": 30.0, "score_120d": 20.0,
         "days_until_earnings": np.nan},
        {"ticker": "DDD", "run_date": "2026-06-26", "model_version": "v0.1_price_volume_only",
         "score_5d": np.nan, "score_20d": np.nan, "score_60d": np.nan, "score_120d": np.nan,
         "days_until_earnings": np.nan},
    ])


def _watchlist_df():
    return pd.DataFrame([
        {"ticker": "AAA", "sector": "Financials", "benchmark": "XLF", "notes": "core"},
        {"ticker": "BBB", "sector": "Energy", "benchmark": "XLE", "notes": "core"},
        {"ticker": "CCC", "sector": "Materials", "benchmark": "XLB", "notes": "core"},
        {"ticker": "DDD", "sector": "Utilities", "benchmark": "XLU", "notes": "core"},
    ])


def test_build_top_setups_rows_excludes_unscored_and_sorts_descending():
    rows = display._build_top_setups_rows(_rankings_df(), _watchlist_df(), top_n=15)
    assert list(rows["ticker"]) == ["AAA", "BBB", "CCC"]
    assert "DDD" not in set(rows["ticker"])


def test_build_top_setups_rows_respects_top_n():
    rows = display._build_top_setups_rows(_rankings_df(), _watchlist_df(), top_n=2)
    assert list(rows["ticker"]) == ["AAA", "BBB"]


def test_build_top_setups_rows_joins_sector_and_attaches_label():
    rows = display._build_top_setups_rows(_rankings_df(), _watchlist_df(), top_n=15)
    aaa = rows[rows["ticker"] == "AAA"].iloc[0]
    assert aaa["sector"] == "Financials"
    assert aaa["label_20d"] == "strong"
    bbb = rows[rows["ticker"] == "BBB"].iloc[0]
    assert bbb["label_20d"] == "decent"


def _review_df_healthy():
    rows = []
    for comp, ic in [
        ("trend_component", 0.10), ("momentum_component_20d", 0.12),
        ("relative_strength_component_20d", 0.15), ("short_momentum_component", 0.01),
        ("setup_component", -0.01),
    ]:
        rows.append({"report_type": "component_correlation", "horizon": "20d", "component": comp,
                      "n": 100, "pearson_ic": ic, "spearman_ic": ic, "suggested_note": None})
    return pd.DataFrame(rows)


def _review_df_inverted():
    rows = []
    for comp, ic in [
        ("trend_component", 0.01), ("momentum_component_20d", 0.02),
        ("relative_strength_component_20d", 0.01), ("short_momentum_component", 0.20),
        ("setup_component", 0.18),
    ]:
        rows.append({"report_type": "component_correlation", "horizon": "20d", "component": comp,
                      "n": 100, "pearson_ic": ic, "spearman_ic": ic, "suggested_note": None})
    return pd.DataFrame(rows)


def test_health_check_line_reports_healthy_pattern():
    line = display._health_check_line(_review_df_healthy(), horizon="20d")
    assert "leading as expected" in line
    assert "WARNING" not in line


def test_health_check_line_flags_inverted_pattern():
    line = display._health_check_line(_review_df_inverted(), horizon="20d")
    assert "WARNING" in line


def _review_df_buckets():
    return pd.DataFrame([
        {"report_type": "bucket", "horizon": "20d", "label": "strong", "n": 50,
         "hit_rate_pct": 60.0},
        {"report_type": "bucket", "horizon": "20d", "label": "weak", "n": 80,
         "hit_rate_pct": 45.0},
        {"report_type": "bucket", "horizon": "5d", "label": "strong", "n": 30,
         "hit_rate_pct": 55.0},
    ])


def test_strong_weak_hit_rates_matches_source_rows():
    out = display._strong_weak_hit_rates(_review_df_buckets(), horizons=("5d", "20d", "60d", "120d"))
    row_20d = out[out["horizon"] == "20d"].iloc[0]
    assert row_20d["strong_hit_rate_pct"] == 60.0
    assert row_20d["weak_hit_rate_pct"] == 45.0

    row_5d = out[out["horizon"] == "5d"].iloc[0]
    assert row_5d["strong_hit_rate_pct"] == 55.0
    assert pd.isna(row_5d["weak_hit_rate_pct"])

    row_60d = out[out["horizon"] == "60d"].iloc[0]
    assert pd.isna(row_60d["strong_hit_rate_pct"])
    assert pd.isna(row_60d["weak_hit_rate_pct"])


def test_component_ic_ranking_sorted_descending():
    ranked = display._component_ic_ranking(_review_df_healthy())
    spearman_values = list(ranked["spearman_ic"])
    assert spearman_values == sorted(spearman_values, reverse=True)
