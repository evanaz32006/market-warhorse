"""Macro / regime data from FRED — free, keyless, decades deep, and BACKFILLABLE.

Why this source is different from the others on the roadmap: analyst estimates and options data can
only be accumulated forward, so they cannot be tested for months. FRED has daily history back to the
1960s and is properly dated, so a hypothesis about regime can be tested TODAY.

TWO HAZARDS, both designed around rather than noted.

1. REVISIONS. FRED's default series returns the LATEST revised value for every past date. For an
   economic STATISTIC — GDP, payrolls, CPI, unemployment — that is a lookahead leak of the worst
   kind: it hands the backtest a number nobody had on the day, and the revision itself is often
   the news. The defence here is categorical rather than careful: this module only ingests
   MARKET-PRICED series (yields, spreads, implied vol), which are observed prices and are never
   revised. `MACRO_SERIES` carries the justification per series, and `assert_market_priced` refuses
   anything not on the list. Statistics would need ALFRED vintage data, which is a different API.

2. REGIME THRESHOLDS. "VIX is high" computed against the full-sample median is lookahead wearing a
   sensible hat — in 2024 nobody knew the 2024-2026 median. Every threshold here is an EXPANDING
   quantile: as of date D it uses only observations up to D, and is undefined until a configured
   minimum history exists. This is the same discipline `patterns._expanding_quantile_mask` applies,
   for the same reason.

A NOTE ON WHAT MACRO CAN AND CANNOT DO HERE, because it determines how it should be used. The model
is a CROSS-SECTIONAL ranker: it orders names within a date. A macro value is identical for every
name on a given date, so adding it as a feature cannot move a single rank — mathematically it can
only shift all scores by a constant. Macro is therefore NOT a ranking feature. It is useful for two
other questions:

  * conditioning — does the ranking's edge differ between regimes? (a testable, pre-registerable
    question, and the one worth asking first)
  * timing — should one be in the market at all? which is the gap sector-neutral ranking
    structurally creates, since a perfect stock-picker still loses money in a falling market.
"""

import io
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from src.config import PARAMS

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

MACRO_CACHE = "data/macro_history.csv"

# Only MARKET-PRICED series. Each entry records why it is safe from revision, because that is the
# invariant a future addition is most likely to break. If a series is not an observed market price,
# it does not belong here — it belongs behind ALFRED vintages.
MACRO_SERIES = {
    # Yield-curve slope. A traded spread between two auction-priced yields; never revised.
    "T10Y2Y": {"label": "yield_curve_10y2y", "why_safe": "market-priced Treasury yields",
               "depth": "1976+"},
    # 10-year constant-maturity Treasury yield. Market-priced; never revised.
    "DGS10": {"label": "treasury_10y", "why_safe": "market-priced Treasury yield",
              "depth": "1962+"},
    # High-yield credit spread (ICE BofA OAS). Computed from traded bond prices; never revised.
    # SHALLOW: the ICE BofA series are licensed, and the free CSV endpoint serves only about three
    # years however the request is framed (`cosd=1900-01-01` changes nothing — measured). So its
    # expanding percentile means "against the last ~3 years", not "against history", and a regime
    # label built on it is correspondingly weaker than one built on VIX or the curve. Stated here
    # because the number looks identical to the deep ones and would otherwise be read as such.
    "BAMLH0A0HYM2": {"label": "hy_credit_spread", "why_safe": "derived from traded bond prices",
                     "depth": "~3y only (licensed series, free endpoint is range-limited)"},
    # Investment-grade credit spread. Same construction, same 3-year limitation.
    "BAMLC0A0CM": {"label": "ig_credit_spread", "why_safe": "derived from traded bond prices",
                   "depth": "~3y only (licensed series, free endpoint is range-limited)"},
    # CBOE VIX close. An index of option prices; never revised. Deep: 1990 onward.
    "VIXCLS": {"label": "vix", "why_safe": "index of traded option prices", "depth": "1990+"},
}


def assert_market_priced(series_id):
    """Refuse any series not on the reviewed list.

    A guard rather than a convention: the failure mode is silent and catastrophic. Adding UNRATE or
    GDP here would backfill revised values into historical features and produce a beautiful, false
    result — exactly the class of bug CLAUDE.md's first invariant exists to prevent."""
    if series_id not in MACRO_SERIES:
        raise ValueError(
            f"{series_id} is not in MACRO_SERIES. Only market-priced series may be used: FRED "
            f"serves the LATEST REVISED value for every past date, so an economic statistic would "
            f"leak numbers nobody had at the time. Add it only after confirming it is an observed "
            f"market price, or use ALFRED vintage data instead.")
    return True


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _cache_path(cache_path=None):
    path = cache_path or MACRO_CACHE
    if os.path.isabs(path):
        return path
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), path)


def fetch_series(series_id, timeout=30):
    """One FRED series as a DataFrame of (date, value), missing observations DROPPED not filled.

    FRED writes "." for a non-observation (a market holiday, or a day the series does not publish).
    Those become NaN and are dropped: a macro series with no reading on a day genuinely has no
    reading, and forward-filling one would invent a market price."""
    assert_market_priced(series_id)
    resp = requests.get(FRED_CSV_URL, params={"id": series_id}, timeout=timeout)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    date_col = df.columns[0]
    df = df.rename(columns={date_col: "date", series_id: "value"})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df["date"] = df["date"].astype(str).str[:10]
    df["series_id"] = series_id
    return df[["series_id", "date", "value"]]


def build_macro_history(series_ids=None, cache_path=None, refresh=False):
    """Fetch every configured series and cache to CSV. Returns the combined frame.

    CSV rather than the database, matching the membership and long-ETF caches: this is research
    input, and nothing in the nightly scoring path should be able to consume it by accident — least
    of all a value that is constant across the cross-section and therefore cannot inform a rank."""
    path = _cache_path(cache_path)
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, dtype={"series_id": str, "date": str})

    frames = []
    for sid in (series_ids or MACRO_SERIES):
        try:
            frame = fetch_series(sid)
            frames.append(frame)
            print("[macro] %-14s %6d observations, %s .. %s"
                  % (sid, len(frame), frame["date"].iloc[0], frame["date"].iloc[-1]))
        except Exception as e:
            print(f"[macro] {sid} failed ({e}) — skipped, nothing invented")
    if not frames:
        return pd.DataFrame(columns=["series_id", "date", "value"])
    out = pd.concat(frames, ignore_index=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.to_csv(path, index=False)
    print("[macro] cached %d observations across %d series -> %s"
          % (len(out), out["series_id"].nunique(), path))
    return out


def as_of_value(history, series_id, as_of_date, max_staleness_days=None):
    """The most recent observation of `series_id` at or before as_of_date.

    THE no-lookahead gate. Also refuses a reading that is too old: a series that stopped publishing
    should go MISSING rather than silently carry a months-stale value forward as if it were current
    (invariant #2 — a stale number presented as current is invented data)."""
    max_staleness_days = (max_staleness_days if max_staleness_days is not None
                          else PARAMS["macro_max_staleness_days"])
    sub = history[(history["series_id"] == series_id) & (history["date"] <= as_of_date)]
    if sub.empty:
        return None, None
    row = sub.loc[sub["date"].idxmax()]
    age = (pd.to_datetime(as_of_date) - pd.to_datetime(row["date"])).days
    if age > max_staleness_days:
        return None, age
    return float(row["value"]), age


def expanding_percentile(values, min_history=None):
    """For each position i, the percentile rank of values[i] within values[:i+1] — CAUSAL.

    A full-sample quantile is the classic regime-classification lookahead: calling 2024 "high VIX"
    using a median that includes 2026 uses information nobody had. NaN until `min_history`
    observations exist, because a percentile computed on twenty points is noise dressed as a regime.
    """
    min_history = min_history if min_history is not None else PARAMS["macro_min_regime_history"]
    values = np.asarray(values, dtype=float)
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        if i + 1 < min_history:
            continue
        window = values[:i + 1]
        window = window[~np.isnan(window)]
        if len(window) < min_history or np.isnan(values[i]):
            continue
        out[i] = 100.0 * (window < values[i]).sum() / len(window)
    return out


def regime_frame(history, series_id):
    """(date, value, expanding_percentile) for one series, date-sorted ascending.

    The percentile column is what a regime label should be built from — never a raw level, whose
    meaning drifts (a 4% ten-year yield meant something different in 2021 than in 2024)."""
    sub = history[history["series_id"] == series_id].sort_values("date")
    if sub.empty:
        return pd.DataFrame(columns=["date", "value", "pctile"])
    return pd.DataFrame({
        "date": sub["date"].values,
        "value": sub["value"].astype(float).values,
        "pctile": expanding_percentile(sub["value"].astype(float).values),
    })


def macro_features_as_of(history, as_of_date):
    """Every configured series as of `as_of_date`, plus its causal percentile. Missing -> None with
    an explicit `*_missing` flag, never a filled value.

    Returned for RESEARCH and CONDITIONING. These must not be fed into the cross-sectional score:
    they are identical for every name on a date, so they cannot change a rank, and including one
    would add a column that looks informative while being arithmetically incapable of doing
    anything."""
    out = {}
    for sid, spec in MACRO_SERIES.items():
        label = spec["label"]
        value, age = as_of_value(history, sid, as_of_date)
        out[label] = value
        out[f"{label}_missing"] = value is None
        out[f"{label}_age_days"] = age
        if value is None:
            out[f"{label}_pctile"] = None
            continue
        frame = regime_frame(history, sid)
        upto = frame[frame["date"] <= as_of_date]
        pct = upto["pctile"].iloc[-1] if not upto.empty else np.nan
        out[f"{label}_pctile"] = None if pd.isna(pct) else float(pct)
    return out
