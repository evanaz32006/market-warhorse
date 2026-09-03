"""Cross-sectional percentiles, component scores, and horizon scores (stage 2).

Missing-input policy (per CLAUDE.md invariant #2 — never invent data): if any raw value
or percentile a component formula needs is None, that component is None for that
ticker/run. Any horizon score that weights a None component is also None. The single
documented exception is long_momentum_component's return_252d -> return_120d fallback.
"""

import math

import pandas as pd

from src.config import (
    COMPONENT_PARAMS,
    EARNINGS_PENALTIES,
    FUNDAMENTAL_PERCENTILE_GROUPS,
    SCORE_LABEL_BANDS,
    SCORE_WEIGHTS,
    SITOUT_COMPONENTS,
)

# Raw fields ranked cross-sectionally as-is (higher raw value -> higher percentile).
_NORMAL_PERCENTILE_FIELDS = [
    "return_5d", "return_10d", "return_20d", "return_60d", "return_120d", "return_252d",
    "relative_strength_5d", "relative_strength_20d", "relative_strength_60d", "relative_strength_120d",
    "volume_ratio_20d",
]
# Risk fields where a LOWER raw value should rank HIGHER (lower risk = better).
_INVERTED_PERCENTILE_FIELDS = ["ATR_pct", "volatility_60d", "max_drawdown_60d"]


def _clean_pct(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return float(value)


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _check_range(component_name, ticker, value, lo=-60, hi=160):
    if value is not None and (value < lo or value > hi):
        print(f"[scoring] WARNING: {component_name} for {ticker} is {value:.1f} before clamping "
              f"— outside the expected envelope [{lo},{hi}], check the formula for a logic error")


def compute_percentiles(features_by_ticker, sector_by_ticker=None,
                        sector_neutral_composites=None, exclude_tickers=None,
                        min_sector_size=None):
    """features_by_ticker: dict[ticker -> raw feature dict] for every ticker included in
    this run (cross-sectional pool). Returns dict[ticker -> percentile dict].

    v0.3 sector-neutral ranking (all new params default to off -> identical v0.1/v0.2 behavior):
    - sector_by_ticker: {ticker -> normalized GICS sector}. Required for the sector-neutral path.
    - sector_neutral_composites: set of composite names (e.g. value_percentile, quality_percentile)
      to rank WITHIN sector instead of cross-sectionally. Everything else stays cross-sectional.
    - exclude_tickers: tickers (benchmark ETFs) excluded from the sector-neutral composites entirely
      -> their composite is None and the component sits out.
    - min_sector_size: a sector must have at least this many members WITH the composite's data
      present to rank within-sector; below it, those members fall back to cross-sectional ranking
      and are flagged sector_rank_fallback=True.
    """
    tickers = list(features_by_ticker.keys())
    df = pd.DataFrame({t: features_by_ticker[t] for t in tickers}).T

    sn_composites = set(sector_neutral_composites or ())
    sec_map = sector_by_ticker or {}
    excl = set(exclude_tickers or ())
    min_size = min_sector_size if min_sector_size is not None else 0

    result = {t: {"sector_rank_fallback": False} for t in tickers}

    for field in _NORMAL_PERCENTILE_FIELDS:
        pct_col = f"{field}_percentile"
        if field in df.columns:
            ranked = pd.to_numeric(df[field], errors="coerce").rank(pct=True, ascending=True) * 100.0
        else:
            ranked = pd.Series([None] * len(tickers), index=tickers)
        for t in tickers:
            result[t][pct_col] = _clean_pct(ranked.get(t))

    for field in _INVERTED_PERCENTILE_FIELDS:
        pct_col = f"{field}_percentile"
        if field in df.columns:
            ranked = pd.to_numeric(df[field], errors="coerce").rank(pct=True, ascending=False) * 100.0
        else:
            ranked = pd.Series([None] * len(tickers), index=tickers)
        for t in tickers:
            result[t][pct_col] = _clean_pct(ranked.get(t))

    if "distance_from_52w_high_pct" in df.columns:
        ranked = pd.to_numeric(df["distance_from_52w_high_pct"], errors="coerce").rank(pct=True, ascending=False) * 100.0
    else:
        ranked = pd.Series([None] * len(tickers), index=tickers)
    for t in tickers:
        value = _clean_pct(ranked.get(t))
        if value is not None and features_by_ticker[t].get("extended_flag") is True:
            value = min(value, 50.0)
        result[t]["distance_from_52w_high_adjusted_percentile"] = value

    # Composite fundamental percentiles (value / quality / short_interest). Each is the MEAN of
    # its present sub-percentiles (pandas leaves missing values as NaN, so they neither rank nor
    # drag the mean); a ticker with none of a family's fields present gets None -> the component
    # sits out. All ranks are 0-100.
    #
    # v0.2 ranks every composite cross-sectionally. v0.3 ranks the composites named in
    # `sn_composites` (value/quality) WITHIN each sector: benchmark ETFs are excluded, sectors with
    # >= min_size members-with-data rank internally, and members of too-small sectors fall back to
    # cross-sectional ranking (flagged sector_rank_fallback). Short interest and all price/volume
    # percentiles above stay cross-sectional either way.
    for composite_name, group in FUNDAMENTAL_PERCENTILE_GROUPS.items():
        invert = group.get("invert", False)
        normal_fields = group.get("fields", [])
        inverted_fields = group.get("invert_fields", [])

        use_sector_neutral = composite_name in sn_composites and bool(sec_map)
        fallback_members = set()
        if use_sector_neutral:
            all_fields = list(normal_fields) + list(inverted_fields)
            big_sectors, fallback_members = _sector_group_info(
                df, all_fields, tickers, sec_map, excl, min_size)

        sub_series = []
        for field in normal_fields:
            if use_sector_neutral:
                sub_series.append(_sector_neutral_field_series(
                    df, field, not invert, tickers, sec_map, excl, big_sectors))
            else:
                sub_series.append(_field_percentile_series(df, field, ascending=not invert, tickers=tickers))
        for field in inverted_fields:
            # explicitly inverted regardless of the group's default direction (lower = better)
            if use_sector_neutral:
                sub_series.append(_sector_neutral_field_series(
                    df, field, False, tickers, sec_map, excl, big_sectors))
            else:
                sub_series.append(_field_percentile_series(df, field, ascending=False, tickers=tickers))

        combined = pd.concat(sub_series, axis=1)
        composite = combined.mean(axis=1, skipna=True)  # NaN only if every sub-percentile is NaN
        for t in tickers:
            value = _clean_pct(composite.get(t))
            result[t][composite_name] = value
            if value is not None and t in fallback_members:
                result[t]["sector_rank_fallback"] = True

    return result


def _field_percentile_series(df, field, ascending, tickers):
    """Cross-sectional percentile (0-100) of one raw field, NaN where the field is missing for
    a ticker. ascending=True -> higher raw ranks higher; ascending=False -> lower raw ranks
    higher (the inverted case). Missing/absent column -> all-NaN series."""
    if field in df.columns:
        return pd.to_numeric(df[field], errors="coerce").rank(pct=True, ascending=ascending) * 100.0
    return pd.Series([float("nan")] * len(tickers), index=tickers)


def _sector_group_info(df, all_fields, tickers, sector_by_ticker, exclude, min_size):
    """For a sector-neutral composite, decide which sectors are big enough to rank within.
    Returns (big_sectors, fallback_members):
    - a ticker "has the composite present" if ANY of its contributing raw fields is non-null;
    - a sector is BIG if it has >= min_size non-excluded members with the composite present;
    - fallback_members = non-excluded, composite-present tickers whose sector is NOT big (they'll
      be ranked cross-sectionally and flagged)."""
    non_excl = [t for t in tickers if t not in exclude]
    present = pd.Series(False, index=non_excl)
    for field in all_fields:
        if field in df.columns:
            col = pd.to_numeric(df[field], errors="coerce").reindex(non_excl)
            present = present | col.notna()

    counts = {}
    for t in non_excl:
        if bool(present.get(t)):
            sec = sector_by_ticker.get(t)
            counts[sec] = counts.get(sec, 0) + 1
    big_sectors = {sec for sec, c in counts.items() if c >= min_size}
    fallback_members = {t for t in non_excl
                        if bool(present.get(t)) and sector_by_ticker.get(t) not in big_sectors}
    return big_sectors, fallback_members


def _sector_neutral_field_series(df, field, ascending, tickers, sector_by_ticker, exclude, big_sectors):
    """Per-field percentile for a sector-neutral composite. Excluded tickers (ETFs) -> NaN.
    Members of BIG sectors are ranked WITHIN their sector; members of too-small sectors fall back
    to a cross-sectional rank over all non-excluded tickers. Same 0-100 scale as the cross-sectional
    helper. Missing raw value -> NaN (skipped by the composite mean)."""
    if field in df.columns:
        raw = pd.to_numeric(df[field], errors="coerce")
    else:
        raw = pd.Series([float("nan")] * len(tickers), index=tickers)

    non_excl = [t for t in tickers if t not in exclude]
    raw_ne = raw.reindex(non_excl)
    # cross-sectional rank over non-excluded (used for small-sector fallback members)
    xs = raw_ne.rank(pct=True, ascending=ascending) * 100.0
    # within-sector rank (NaN raw stays NaN; groups are the normalized sector labels)
    sec = pd.Series({t: sector_by_ticker.get(t) for t in non_excl})
    within = raw_ne.groupby(sec).rank(pct=True, ascending=ascending) * 100.0

    out = pd.Series([float("nan")] * len(tickers), index=tickers)
    for t in non_excl:
        out[t] = within.get(t) if sector_by_ticker.get(t) in big_sectors else xs.get(t)
    return out


# ---------------------------------------------------------------------------
# Component scores
# ---------------------------------------------------------------------------

def trend_component(features, params, ticker=None):
    required = ["latest_close", "SMA20", "SMA50", "SMA200"]
    if any(features.get(k) is None for k in required):
        return None
    close, sma20, sma50, sma200 = (features["latest_close"], features["SMA20"],
                                    features["SMA50"], features["SMA200"])
    pts = params["points_per_condition"]
    score = 0
    score += pts if close > sma20 else 0
    score += pts if close > sma50 else 0
    score += pts if close > sma200 else 0
    score += pts if sma20 > sma50 else 0
    score += pts if sma50 > sma200 else 0
    _check_range("trend_component", ticker, score)
    return _clamp(score)


def short_momentum_component(features, percentiles, params, ticker=None):
    needed = ["return_5d_percentile", "return_10d_percentile", "return_20d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_return_5d_pct"] * percentiles["return_5d_percentile"]
              + params["w_return_10d_pct"] * percentiles["return_10d_percentile"]
              + params["w_return_20d_pct"] * percentiles["return_20d_percentile"])
    if features.get("return_5d") is not None and features["return_5d"] < 0:
        score -= params["penalty_return_5d_negative"]
    if features.get("return_10d") is not None and features["return_10d"] < 0:
        score -= params["penalty_return_10d_negative"]
    _check_range("short_momentum_component", ticker, score)
    return _clamp(score)


def momentum_component_20d(features, percentiles, params, ticker=None):
    needed = ["return_20d_percentile", "return_60d_percentile", "return_10d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_return_20d_pct"] * percentiles["return_20d_percentile"]
              + params["w_return_60d_pct"] * percentiles["return_60d_percentile"]
              + params["w_return_10d_pct"] * percentiles["return_10d_percentile"])
    if features.get("return_20d") is not None and features["return_20d"] < 0:
        score -= params["penalty_return_20d_negative"]
    _check_range("momentum_component_20d", ticker, score)
    return _clamp(score)


def medium_momentum_component(features, percentiles, params, ticker=None):
    needed = ["return_60d_percentile", "return_120d_percentile", "return_20d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_return_60d_pct"] * percentiles["return_60d_percentile"]
              + params["w_return_120d_pct"] * percentiles["return_120d_percentile"]
              + params["w_return_20d_pct"] * percentiles["return_20d_percentile"])
    if features.get("return_60d") is not None and features["return_60d"] < 0:
        score -= params["penalty_return_60d_negative"]
    _check_range("medium_momentum_component", ticker, score)
    return _clamp(score)


def long_momentum_component(features, percentiles, params, ticker=None):
    needed = ["return_120d_percentile", "return_60d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    return_252d_pct = percentiles.get("return_252d_percentile")
    if return_252d_pct is None:
        # Documented fallback: use return_120d_percentile in place of the missing 252d.
        return_252d_pct = percentiles["return_120d_percentile"]
    score = (params["w_return_120d_pct"] * percentiles["return_120d_percentile"]
              + params["w_return_252d_pct"] * return_252d_pct
              + params["w_return_60d_pct"] * percentiles["return_60d_percentile"])
    if features.get("return_120d") is not None and features["return_120d"] < 0:
        score -= params["penalty_return_120d_negative"]
    _check_range("long_momentum_component", ticker, score)
    return _clamp(score)


def relative_strength_component_5d(features, percentiles, params, ticker=None):
    needed = ["relative_strength_5d_percentile", "relative_strength_20d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_rs_5d_pct"] * percentiles["relative_strength_5d_percentile"]
              + params["w_rs_20d_pct"] * percentiles["relative_strength_20d_percentile"])
    if features.get("relative_strength_5d") is not None and features["relative_strength_5d"] < 0:
        score -= params["penalty_rs_5d_negative"]
    _check_range("relative_strength_component_5d", ticker, score)
    return _clamp(score)


def relative_strength_component_20d(features, percentiles, params, ticker=None):
    needed = ["relative_strength_20d_percentile", "relative_strength_60d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_rs_20d_pct"] * percentiles["relative_strength_20d_percentile"]
              + params["w_rs_60d_pct"] * percentiles["relative_strength_60d_percentile"])
    if features.get("relative_strength_20d") is not None and features["relative_strength_20d"] < 0:
        score -= params["penalty_rs_20d_negative"]
    if features.get("relative_strength_60d") is not None and features["relative_strength_60d"] < 0:
        score -= params["penalty_rs_60d_negative"]
    _check_range("relative_strength_component_20d", ticker, score)
    return _clamp(score)


def relative_strength_component_60d(features, percentiles, params, ticker=None):
    needed = ["relative_strength_60d_percentile", "relative_strength_120d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_rs_60d_pct"] * percentiles["relative_strength_60d_percentile"]
              + params["w_rs_120d_pct"] * percentiles["relative_strength_120d_percentile"])
    if features.get("relative_strength_60d") is not None and features["relative_strength_60d"] < 0:
        score -= params["penalty_rs_60d_negative"]
    _check_range("relative_strength_component_60d", ticker, score)
    return _clamp(score)


def relative_strength_component_120d(features, percentiles, params, ticker=None):
    needed = ["relative_strength_120d_percentile", "relative_strength_60d_percentile"]
    if any(percentiles.get(k) is None for k in needed):
        return None
    score = (params["w_rs_120d_pct"] * percentiles["relative_strength_120d_percentile"]
              + params["w_rs_60d_pct"] * percentiles["relative_strength_60d_percentile"])
    if features.get("relative_strength_120d") is not None and features["relative_strength_120d"] < 0:
        score -= params["penalty_rs_120d_negative"]
    _check_range("relative_strength_component_120d", ticker, score)
    return _clamp(score)


def volume_behavior_component(features, params, ticker=None):
    required = ["volume_ratio_20d", "return_1d", "high_volume_up_days_20d",
                "high_volume_down_days_20d", "weak_close_flag", "strong_close_flag"]
    if any(features.get(k) is None for k in required):
        return None
    vr, r1 = features["volume_ratio_20d"], features["return_1d"]
    t1, t2, t3 = params["ratio_threshold_1"], params["ratio_threshold_2"], params["ratio_threshold_3"]
    score = params["base"]

    if vr > t1 and r1 > 0:
        score += params["up_day_bonus_at_threshold_1"]
        if vr > t2:
            score += params["up_day_bonus_at_threshold_2"]
            if vr > t3:
                score += params["up_day_bonus_at_threshold_3"]
    if vr > t2 and r1 < 0:
        score += params["down_day_penalty_at_threshold_2"]
        if vr > t3:
            score += params["down_day_penalty_at_threshold_3"]

    score += params["high_vol_day_diff_multiplier"] * (
        features["high_volume_up_days_20d"] - features["high_volume_down_days_20d"]
    )

    close_ratio_threshold = params["close_flag_ratio_threshold"]
    if features["weak_close_flag"] and vr > close_ratio_threshold:
        score += params["weak_close_penalty"]
    if features["strong_close_flag"] and vr > close_ratio_threshold:
        score += params["strong_close_bonus"]

    _check_range("volume_behavior_component", ticker, score)
    return _clamp(score)


def risk_component(features, percentiles, params, ticker=None):
    needed_pct = ["ATR_pct_percentile", "volatility_60d_percentile",
                  "max_drawdown_60d_percentile", "distance_from_52w_high_adjusted_percentile"]
    needed_raw = ["extended_flag", "latest_close", "SMA50"]
    if any(percentiles.get(k) is None for k in needed_pct) or any(features.get(k) is None for k in needed_raw):
        return None
    score = (params["w_atr_pct_percentile"] * percentiles["ATR_pct_percentile"]
              + params["w_volatility_60d_percentile"] * percentiles["volatility_60d_percentile"]
              + params["w_max_drawdown_60d_percentile"] * percentiles["max_drawdown_60d_percentile"]
              + params["w_distance_from_52w_high_adjusted_percentile"] * percentiles["distance_from_52w_high_adjusted_percentile"])
    if features["extended_flag"]:
        score -= params["penalty_extended"]
    if features["latest_close"] < features["SMA50"]:
        score -= params["penalty_below_sma50"]
    _check_range("risk_component", ticker, score)
    return _clamp(score)


def setup_component(features, params, ticker=None):
    required = ["latest_close", "SMA20", "SMA50", "not_extended_flag", "near_20d_high",
                "near_60d_high", "pullback_above_SMA50", "failed_breakout_flag"]
    if any(features.get(k) is None for k in required):
        return None
    score = 0
    if features["latest_close"] > features["SMA20"]:
        score += params["points_close_above_sma20"]
    if features["latest_close"] > features["SMA50"]:
        score += params["points_close_above_sma50"]
    if features["not_extended_flag"]:
        score += params["points_not_extended"]
    if features["near_20d_high"]:
        score += params["points_near_20d_high"]
    if features["near_60d_high"]:
        score += params["points_near_60d_high"]
    if features["pullback_above_SMA50"]:
        score += params["points_pullback_above_sma50"]
    if features["failed_breakout_flag"]:
        score += params["penalty_failed_breakout"]
    _check_range("setup_component", ticker, score)
    return _clamp(score)


def market_regime_component(features, params, ticker=None):
    required = ["benchmark_above_SMA20", "benchmark_above_SMA50", "benchmark_above_SMA200",
                "benchmark_return_20d", "benchmark_return_60d", "benchmark_vol_high_flag"]
    if any(features.get(k) is None for k in required):
        return None
    score = 0
    if features["benchmark_above_SMA20"]:
        score += params["points_benchmark_above_sma20"]
    if features["benchmark_above_SMA50"]:
        score += params["points_benchmark_above_sma50"]
    if features["benchmark_above_SMA200"]:
        score += params["points_benchmark_above_sma200"]
    if features["benchmark_return_20d"] > 0:
        score += params["points_benchmark_return_20d_positive"]
    if features["benchmark_return_60d"] > 0:
        score += params["points_benchmark_return_60d_positive"]
    if features["benchmark_vol_high_flag"]:
        score += params["penalty_benchmark_vol_high"]
    _check_range("market_regime_component", ticker, score)
    return _clamp(score)


def _fundamental_component(percentiles, params, name, ticker=None):
    """value/quality/short_interest components are simply the (already 0-100) composite
    percentile passed through and clamped. None composite -> None component (the family sits
    out for this ticker), never defaulted to a neutral 50 (that would invent a reading)."""
    pct = percentiles.get(params["percentile_field"])
    if pct is None:
        return None
    _check_range(name, ticker, pct)
    return _clamp(pct)


def value_component(percentiles, params, ticker=None):
    return _fundamental_component(percentiles, params, "value_component", ticker)


def quality_component(percentiles, params, ticker=None):
    return _fundamental_component(percentiles, params, "quality_component", ticker)


def short_interest_component(percentiles, params, ticker=None):
    return _fundamental_component(percentiles, params, "short_interest_component", ticker)


def compute_all_components(features, percentiles, params=None, ticker=None):
    cp = params or COMPONENT_PARAMS
    return {
        "trend_component": trend_component(features, cp["trend_component"], ticker),
        "short_momentum_component": short_momentum_component(features, percentiles, cp["short_momentum_component"], ticker),
        "momentum_component_20d": momentum_component_20d(features, percentiles, cp["momentum_component_20d"], ticker),
        "medium_momentum_component": medium_momentum_component(features, percentiles, cp["medium_momentum_component"], ticker),
        "long_momentum_component": long_momentum_component(features, percentiles, cp["long_momentum_component"], ticker),
        "relative_strength_component_5d": relative_strength_component_5d(features, percentiles, cp["relative_strength_component_5d"], ticker),
        "relative_strength_component_20d": relative_strength_component_20d(features, percentiles, cp["relative_strength_component_20d"], ticker),
        "relative_strength_component_60d": relative_strength_component_60d(features, percentiles, cp["relative_strength_component_60d"], ticker),
        "relative_strength_component_120d": relative_strength_component_120d(features, percentiles, cp["relative_strength_component_120d"], ticker),
        "volume_behavior_component": volume_behavior_component(features, cp["volume_behavior_component"], ticker),
        "risk_component": risk_component(features, percentiles, cp["risk_component"], ticker),
        "setup_component": setup_component(features, cp["setup_component"], ticker),
        "market_regime_component": market_regime_component(features, cp["market_regime_component"], ticker),
        "value_component": value_component(percentiles, cp["value_component"], ticker),
        "quality_component": quality_component(percentiles, cp["quality_component"], ticker),
        "short_interest_component": short_interest_component(percentiles, cp["short_interest_component"], ticker),
    }


def compute_horizon_scores(components, days_until_earnings=None, earnings_risk_unknown=True,
                            weights=None, earnings_penalties=None, ticker=None):
    weights = weights or SCORE_WEIGHTS
    earnings_penalties = earnings_penalties or EARNINGS_PENALTIES

    apply_penalty = (not earnings_risk_unknown and days_until_earnings is not None
                      and 0 <= days_until_earnings <= 5)

    result = {}
    for horizon_key, weight_map in weights.items():
        horizon_suffix = horizon_key.split("_", 1)[1]  # "score_5d" -> "5d"

        # A MANDATORY (price/volume) component that is None still nulls the whole horizon,
        # exactly as in v0.1 — those inputs are always expected to be present. Only the
        # SITOUT_COMPONENTS (value/quality/short_interest) may be absent; when they are, they
        # drop out and the surviving weights are renormalized to sum to 1, so a ticker with no
        # fundamentals still gets a valid price/volume-only score (never defaulted to neutral).
        mandatory = [c for c in weight_map if c not in SITOUT_COMPONENTS]
        if any(components.get(c) is None for c in mandatory):
            result[horizon_key] = None
            continue

        present = {c: w for c, w in weight_map.items() if components.get(c) is not None}
        total_weight = sum(present.values())
        if total_weight <= 0:  # defensive: should never happen (mandatory weights > 0)
            result[horizon_key] = None
            continue
        raw_score = sum(components[c] * w for c, w in present.items()) / total_weight
        penalty = earnings_penalties[horizon_suffix] if apply_penalty else 0
        score = raw_score - penalty
        if isinstance(score, float) and math.isnan(score):
            print(f"[scoring] WARNING: {horizon_key} for {ticker} is NaN despite no missing "
                  f"components — investigate a possible formula bug")
            result[horizon_key] = None
        else:
            result[horizon_key] = _clamp(score)
    return result


def label_for_score(score, bands=None):
    """Bands are defined in config.py with integer (lo, hi) pairs per the spec (e.g.
    65-79 decent, 80-100 strong). Scores are continuous floats, so a literal lo<=x<=hi
    check leaves gaps (e.g. 79.2 matches neither band). Instead, treat each band's lo as
    a threshold and pick the highest one the score clears — the bands are meant to
    partition the full range contiguously, not leave gaps between them."""
    if score is None:
        return None
    bands = bands or SCORE_LABEL_BANDS
    ordered = sorted(bands.items(), key=lambda item: item[1][0], reverse=True)
    for label, (lo, _hi) in ordered:
        if score >= lo:
            return label
    return None
