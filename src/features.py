"""As-of-date raw feature computation for a single ticker (stage 1 — no percentiles,
components, or horizon scores yet; those need the whole watchlist and live in scoring.py).

No-lookahead contract: every input frame is truncated to `as_of_date` BEFORE any
rolling/window math runs, so a caller accidentally passing future rows can never leak
into the result.
"""

import math

import numpy as np
import pandas as pd

from src.config import (
    FUNDAMENTAL_FIELDS,
    FUNDAMENTAL_PERCENTILE_GROUPS,
    NON_NEGATIVE_VALUATION_FIELDS,
    PARAMS,
)


def _to_frame(price_data):
    """Accept either a DataFrame or a list of dicts (as returned by storage.load_price_history)
    and return a date-sorted DataFrame with a 'date' column of pandas Timestamps."""
    df = price_data if isinstance(price_data, pd.DataFrame) else pd.DataFrame(price_data)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _truncate(price_data, as_of_date):
    df = _to_frame(price_data)
    as_of = pd.Timestamp(as_of_date)
    return df[df["date"] <= as_of].reset_index(drop=True)


def _pct(a, b):
    if a is None or b is None or b == 0 or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return None
    return ((a - b) / b) * 100.0


def _clean(value):
    """Convert numpy/NaN scalars to plain Python None/float for storage and equality tests."""
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) else float(value)
    return value


def _trend_features(tdf, params, prefix=""):
    """SMA / close-vs-SMA fields. prefix is unused for the main ticker; kept for symmetry
    with benchmark feature computation."""
    out = {}
    close = tdf["close"]
    n = len(tdf)
    sma = {}
    for w in params["sma_windows"]:
        if n >= w:
            sma[w] = close.tail(w).mean()
        else:
            sma[w] = None
    out["SMA20"], out["SMA50"], out["SMA200"] = sma.get(20), sma.get(50), sma.get(200)

    latest_close = close.iloc[-1]
    out["close_vs_SMA20_pct"] = _pct(latest_close, out["SMA20"])
    out["close_vs_SMA50_pct"] = _pct(latest_close, out["SMA50"])
    out["close_vs_SMA200_pct"] = _pct(latest_close, out["SMA200"])
    out["SMA20_vs_SMA50_pct"] = _pct(out["SMA20"], out["SMA50"])
    out["SMA50_vs_SMA200_pct"] = _pct(out["SMA50"], out["SMA200"])
    return out


def _return_features(tdf, params):
    out = {}
    close = tdf["close"]
    n = len(tdf)
    latest_close = close.iloc[-1]
    for w in params["return_windows"]:
        if n > w:
            past_close = close.iloc[-1 - w]
            out[f"return_{w}d"] = (latest_close / past_close) - 1.0 if past_close != 0 else None
        else:
            out[f"return_{w}d"] = None
    out["return_252d_missing"] = out.get("return_252d") is None
    return out


def _volume_features(tdf, params):
    out = {}
    close, high, low, volume = tdf["close"], tdf["high"], tdf["low"], tdf["volume"]
    n = len(tdf)
    daily_return = close.pct_change()

    avg_vol = {}
    for w in params["volume_avg_windows"]:
        avg_vol[w] = volume.tail(w).mean() if n >= w else None
    out["volume_ratio_20d"] = (volume.iloc[-1] / avg_vol[20]) if avg_vol.get(20) not in (None, 0) else None
    out["volume_ratio_60d"] = (volume.iloc[-1] / avg_vol[60]) if avg_vol.get(60) not in (None, 0) else None

    # TRADEABILITY, in dollars. Every other volume feature here is a RATIO - scale-free by design, so
    # a thinly traded microcap and a mega-cap can look identical. That was harmless while the universe
    # was the S&P 500; it is not once small caps are in, because a name that trades $200k/day cannot
    # absorb a real order and a backtest that fills in it is fiction. Measured and FLAGGED here; the
    # row is still scored and stored, and only the portfolio simulation excludes it (invariant #2 -
    # surface the problem, never silently drop the data).
    if n >= 20:
        out["dollar_volume_20d"] = float((close.tail(20) * volume.tail(20)).mean())
        out["illiquid_flag"] = int(out["dollar_volume_20d"] < params["min_dollar_volume_20d"])
    else:
        out["dollar_volume_20d"] = None
        out["illiquid_flag"] = None       # unknown, NOT "liquid" - absence of evidence is not evidence

    high_vol_threshold_ratio = params["high_volume_ratio_threshold"]
    if n >= 20 and avg_vol[20] not in (None, 0):
        last20_ret = daily_return.tail(20)
        last20_vol = volume.tail(20)
        thresh = high_vol_threshold_ratio * avg_vol[20]
        out["high_volume_up_days_20d"] = int(((last20_ret > 0) & (last20_vol > thresh)).sum())
        out["high_volume_down_days_20d"] = int(((last20_ret < 0) & (last20_vol > thresh)).sum())

        up_vol_sum = last20_vol[last20_ret > 0].sum()
        down_vol_sum = last20_vol[last20_ret < 0].sum()
        if down_vol_sum > 0:
            out["up_volume_vs_down_volume_20d"] = min(up_vol_sum / down_vol_sum, params["up_down_volume_cap"])
        else:
            out["up_volume_vs_down_volume_20d"] = params["up_down_volume_cap"]
    else:
        out["high_volume_up_days_20d"] = None
        out["high_volume_down_days_20d"] = None
        out["up_volume_vs_down_volume_20d"] = None

    last_high, last_low, last_close = high.iloc[-1], low.iloc[-1], close.iloc[-1]
    if last_high == last_low:
        out["close_position"] = 0.5
    else:
        out["close_position"] = (last_close - last_low) / (last_high - last_low)
    out["weak_close_flag"] = out["close_position"] < params["close_position_weak_threshold"]
    out["strong_close_flag"] = out["close_position"] > params["close_position_strong_threshold"]
    return out


def _true_range_series(tdf):
    high, low, close = tdf["high"], tdf["low"], tdf["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    # First bar of the whole series has no prior close; fall back to high-low for it only.
    if len(tr) and pd.isna(tr.iloc[0]):
        tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def _max_drawdown_pct(close_window):
    """Positive-magnitude max peak-to-trough decline within the given window (peak must
    be inside the window itself, not from before it)."""
    if len(close_window) < 2:
        return None
    running_max = close_window.cummax()
    drawdown = (close_window - running_max) / running_max
    return float(-drawdown.min() * 100.0)


def _risk_features(tdf, params):
    out = {}
    close = tdf["close"]
    n = len(tdf)
    atr_window = params["atr_window"]
    ann_factor = math.sqrt(params["trading_days_per_year"])

    if n >= atr_window:
        tr = _true_range_series(tdf)
        out["ATR14"] = float(tr.tail(atr_window).mean())
        out["ATR_pct"] = out["ATR14"] / close.iloc[-1] if close.iloc[-1] else None
    else:
        out["ATR14"] = None
        out["ATR_pct"] = None

    daily_return = close.pct_change()
    for w in params["volatility_windows"]:
        if n >= w + 1:
            out[f"volatility_{w}d"] = float(daily_return.tail(w).std() * ann_factor)
        else:
            out[f"volatility_{w}d"] = None

    dvw = params["downside_volatility_window"]
    if n >= dvw + 1:
        neg_returns = daily_return.tail(dvw)
        neg_returns = neg_returns[neg_returns < 0]
        out["downside_volatility_20d"] = float(neg_returns.std() * ann_factor) if len(neg_returns) >= 2 else None
    else:
        out["downside_volatility_20d"] = None

    for w in params["max_drawdown_windows"]:
        if n >= w:
            out[f"max_drawdown_{w}d"] = _max_drawdown_pct(close.tail(w))
        else:
            out[f"max_drawdown_{w}d"] = None

    week52 = params["week52_window"]
    window = close.tail(min(n, week52))
    high_52w, low_52w = window.max(), window.min()
    latest_close = close.iloc[-1]
    out["distance_from_52w_high_pct"] = ((high_52w - latest_close) / high_52w) * 100.0 if high_52w else None
    out["distance_from_52w_low_pct"] = ((latest_close - low_52w) / low_52w) * 100.0 if low_52w else None
    return out


def _setup_features(tdf, params, trend_out, risk_out):
    out = {}
    high, close = tdf["high"], tdf["close"]
    n = len(tdf)
    latest_close = close.iloc[-1]

    if n >= 20:
        high20 = high.tail(20).max()
        out["near_20d_high"] = bool(latest_close >= params["near_20d_high_pct"] * high20)
    else:
        out["near_20d_high"], high20 = None, None

    if n >= 60:
        high60 = high.tail(60).max()
        out["near_60d_high"] = bool(latest_close >= params["near_60d_high_pct"] * high60)
    else:
        out["near_60d_high"] = None

    sma50 = trend_out.get("SMA50")
    if sma50 is not None and high20 is not None:
        pct_below_20d_high = ((high20 - latest_close) / high20) * 100.0
        out["pullback_above_SMA50"] = bool(
            latest_close > sma50 and params["pullback_min_pct"] <= pct_below_20d_high <= params["pullback_max_pct"]
        )
    else:
        out["pullback_above_SMA50"] = None

    lookback = params["failed_breakout_lookback_days"]
    if n >= 20 + lookback:
        # Was a NEW 20-session high set within the last `lookback` sessions (i.e. that
        # session's high exceeded the high of the 20 sessions strictly before it), and is
        # the latest close now >= threshold% below that high?
        broken_high_value = None
        for p in range(n - lookback, n):
            prior20_high = high.iloc[p - 20:p].max()
            if high.iloc[p] > prior20_high:
                broken_high_value = high.iloc[p] if broken_high_value is None else max(broken_high_value, high.iloc[p])
        if broken_high_value is not None:
            pct_below = ((broken_high_value - latest_close) / broken_high_value) * 100.0
            out["failed_breakout_flag"] = bool(pct_below >= params["failed_breakout_threshold_pct"])
        else:
            out["failed_breakout_flag"] = False
    else:
        out["failed_breakout_flag"] = None

    if trend_out.get("close_vs_SMA20_pct") is not None:
        out["extended_flag"] = bool(trend_out["close_vs_SMA20_pct"] > params["extended_pct"])
        out["not_extended_flag"] = not out["extended_flag"]
    else:
        out["extended_flag"] = None
        out["not_extended_flag"] = None
    return out


def _benchmark_regime_features(bdf, params):
    """Computed by running the same as-of-truncated trend/return logic on the
    benchmark's own price series."""
    out = {}
    trend = _trend_features(bdf, params)
    rets = _return_features(bdf, params)
    n = len(bdf)
    daily_return = bdf["close"].pct_change()

    out["benchmark_above_SMA20"] = (trend["close_vs_SMA20_pct"] > 0) if trend["close_vs_SMA20_pct"] is not None else None
    out["benchmark_above_SMA50"] = (trend["close_vs_SMA50_pct"] > 0) if trend["close_vs_SMA50_pct"] is not None else None
    out["benchmark_above_SMA200"] = (trend["close_vs_SMA200_pct"] > 0) if trend["close_vs_SMA200_pct"] is not None else None

    for w in params["benchmark_return_windows"]:
        out[f"benchmark_return_{w}d"] = rets.get(f"return_{w}d")
    for w in params["rs_windows"]:
        out[f"benchmark_return_{w}d"] = rets.get(f"return_{w}d")

    vol_window = params["benchmark_volatility_window"]
    if n >= vol_window + 1:
        out["benchmark_volatility_20d"] = float(daily_return.tail(vol_window).std() * math.sqrt(params["trading_days_per_year"]))
    else:
        out["benchmark_volatility_20d"] = None

    trailing_window = params["benchmark_vol_trailing_window"]
    if n >= vol_window + 1 and out["benchmark_volatility_20d"] is not None:
        rolling_vol = daily_return.rolling(vol_window).std() * math.sqrt(params["trading_days_per_year"])
        trailing = rolling_vol.tail(trailing_window).dropna()
        if len(trailing) >= 10:
            pctile_rank = (trailing <= out["benchmark_volatility_20d"]).mean() * 100.0
            out["benchmark_vol_high_flag"] = bool(pctile_rank > params["benchmark_vol_high_percentile"])
        else:
            out["benchmark_vol_high_flag"] = None
    else:
        out["benchmark_vol_high_flag"] = None
    return out


def _family_fields(group):
    """All raw fields that feed a FUNDAMENTAL_PERCENTILE_GROUPS composite (normal + inverted)."""
    return list(group.get("fields", [])) + list(group.get("invert_fields", []))


def compute_fundamental_features(raw_fundamentals):
    """Clean the raw per-ticker fundamentals (from data.fetch_fundamentals) into snapshot
    fields, applying the no-invent-data rules, and derive the sit-out missing flags.

    raw_fundamentals: dict[field -> value or None]. Pass {} on backfill (fundamentals are not
    historically reconstructable) — every field then comes back None and every *_missing flag
    True, so the value/quality/short components sit out and the ticker keeps a valid
    price/volume-only score.

    Rules enforced here:
    - A NEGATIVE (or zero) valuation ratio is NOT "cheap" — it means no/again earnings and is
      scrubbed to None (missing) rather than ranked as a misleadingly good low value.
    - A family (value / quality / short_interest) is flagged missing when ALL of its
      contributing raw fields are None, so the corresponding component sits out downstream.
    - fundamentals_missing is True only when the row carries no fundamental data at all.

    Returns a flat dict of the FUNDAMENTAL_FIELDS plus fundamentals_missing / value_missing /
    quality_missing / short_interest_missing.
    """
    raw = raw_fundamentals or {}
    out = {}
    for field in FUNDAMENTAL_FIELDS:
        value = _clean(raw.get(field))
        if field in NON_NEGATIVE_VALUATION_FIELDS and value is not None and value <= 0:
            # negative/zero P/E, P/S, EV/EBITDA, P/B -> not meaningful -> treat as missing.
            value = None
        out[field] = value

    value_fields = _family_fields(FUNDAMENTAL_PERCENTILE_GROUPS["value_percentile"])
    quality_fields = _family_fields(FUNDAMENTAL_PERCENTILE_GROUPS["quality_percentile"])
    short_fields = _family_fields(FUNDAMENTAL_PERCENTILE_GROUPS["short_interest_percentile"])

    out["value_missing"] = all(out.get(f) is None for f in value_fields)
    out["quality_missing"] = all(out.get(f) is None for f in quality_fields)
    out["short_interest_missing"] = all(out.get(f) is None for f in short_fields)
    out["fundamentals_missing"] = all(out.get(f) is None for f in FUNDAMENTAL_FIELDS)
    return out


def compute_features(ticker, benchmark, as_of_date, price_history, benchmark_history, params=None):
    """Compute the full raw-feature set for `ticker` as of `as_of_date`, using only price
    data with date <= as_of_date from both `price_history` and `benchmark_history`.

    price_history / benchmark_history: DataFrame or list-of-dicts with date/open/high/low/close/volume.
    Returns a flat dict of feature_name -> value (None for missing/insufficient-history fields).
    """
    params = params or PARAMS
    tdf = _truncate(price_history, as_of_date)
    bdf = _truncate(benchmark_history, as_of_date)

    if len(tdf) == 0:
        raise ValueError(f"No price data for {ticker} on or before {as_of_date} — cannot compute features")
    if len(bdf) == 0:
        raise ValueError(f"No price data for benchmark {benchmark} on or before {as_of_date} — cannot compute features")

    out = {}
    trend = _trend_features(tdf, params)
    rets = _return_features(tdf, params)
    vol = _volume_features(tdf, params)
    risk = _risk_features(tdf, params)
    setup = _setup_features(tdf, params, trend, risk)
    regime = _benchmark_regime_features(bdf, params)

    out["latest_close"] = float(tdf["close"].iloc[-1])
    out.update(trend)
    out.update(rets)
    out.update(vol)
    out.update(risk)
    out.update(setup)
    out.update(regime)

    for w in params["rs_windows"]:
        stock_ret = out.get(f"return_{w}d")
        bench_ret = out.get(f"benchmark_return_{w}d")
        if stock_ret is not None and bench_ret is not None:
            out[f"relative_strength_{w}d"] = stock_ret - bench_ret
        else:
            out[f"relative_strength_{w}d"] = None

    # Fail loud: a feature must not be NaN if the ticker had enough history for its window.
    n = len(tdf)
    insufficient_log = []
    for key, value in list(out.items()):
        cleaned = _clean(value)
        out[key] = cleaned
        if isinstance(value, float) and math.isnan(value):
            insufficient_log.append(key)
        elif cleaned is None and not key.endswith("_missing"):
            insufficient_log.append(key)
    if insufficient_log:
        print(f"[features] {ticker} as of {as_of_date}: null fields (insufficient history, n={n} bars): {insufficient_log}")

    return out
