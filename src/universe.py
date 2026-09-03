"""S&P 500 universe expansion: pulls the constituent list (ticker + GICS sector) from a
free, auto-updated source, assigns each new ticker a benchmark ETF by sector, and merges
it into the hand-curated watchlist without ever touching an existing row. Per CLAUDE.md
invariant #2, a fetch failure never invents constituents — it falls back to the last
cached copy, or to "nothing new this run" if no cache exists yet.
"""

import os

import pandas as pd
import requests
from io import StringIO

from src.config import (INDEX_SOURCES, PARAMS, SECTOR_BENCHMARK_MAP,
                        SEMICONDUCTOR_SUB_INDUSTRIES, SIZE_BENCHMARKED_BUCKETS,
                        SIZE_BUCKET_BENCHMARK)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _resolve_cache_path(cache_path):
    cache_path = cache_path or PARAMS["sp500_cache_path"]
    if os.path.isabs(cache_path):
        return cache_path
    return os.path.join(PROJECT_ROOT, cache_path)


CONSTITUENT_COLUMNS = ["Symbol", "GICS Sector", "GICS Sub-Industry"]


def _pick_constituents_table(tables):
    """The first HTML table carrying BOTH a Symbol and a GICS Sector column.

    Wikipedia constituent pages also contain a change-history table and a navbox; selecting by
    position would silently pick the wrong one the day the page is reordered, and a universe built
    from a navbox is not a universe. Selecting by required columns fails loudly instead."""
    for t in tables:
        cols = {str(c).strip().lower() for c in t.columns}
        if "symbol" in cols and any("gics sector" in c for c in cols):
            return t
    return None


def fetch_index_constituents(index_name, cache_path=None, url=None, timeout=None):
    """Constituents for one index as a DataFrame of CONSTITUENT_COLUMNS, plus a size_bucket.

    Same live -> cache -> empty discipline as the original S&P 500 fetch, with one fix: the cache
    now stores the PARSED frame rather than the raw response body. The old code wrote the body
    before parsing it, so any 200-with-garbage response (a captive portal, an error page rendered
    with a 200, a redirect to HTML) permanently poisoned the cache with something that would never
    parse again. Writing only after a successful parse means the cache always holds usable data.

    Returns an EMPTY frame rather than inventing constituents when both live and cache fail."""
    spec = INDEX_SOURCES[index_name]
    cache_path = _resolve_cache_path(cache_path or spec["cache_path"])
    url = url or spec["url"]
    timeout = timeout or PARAMS["index_fetch_timeout_sec"]
    bucket = spec["size_bucket"]

    df = None
    try:
        headers = {"User-Agent": PARAMS["index_fetch_user_agent"]}
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        if spec["kind"] == "csv":
            df = pd.read_csv(StringIO(resp.text))
        else:
            df = _pick_constituents_table(pd.read_html(StringIO(resp.text)))
            if df is None:
                raise ValueError("no table with both Symbol and GICS Sector columns")
        df = df[CONSTITUENT_COLUMNS]
        if df.empty:
            raise ValueError("source returned zero constituents")
    except Exception as e:
        print(f"[universe] WARNING: could not fetch {index_name} constituents ({e}); "
              f"falling back to cache at {cache_path}")
        if os.path.exists(cache_path):
            df = pd.read_csv(cache_path)[CONSTITUENT_COLUMNS]
        else:
            print(f"[universe] WARNING: no cached {index_name} list either - adding zero new "
                  f"tickers from it this run (never inventing constituents).")
            out = pd.DataFrame(columns=CONSTITUENT_COLUMNS)
            out["size_bucket"] = pd.Series(dtype=str)
            return out
    else:
        # only reached on a clean parse, so the cache can never hold an unparseable body
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        df.to_csv(cache_path, index=False)

    df = df.copy()
    df["size_bucket"] = bucket
    df["source_index"] = index_name       # provenance: keeps the existing "<index>_auto" notes convention
    return df


def fetch_all_constituents(index_names=None):
    """Every configured index, concatenated, first-listing-wins on duplicates.

    A ticker in two indices is a data error rather than a real dual membership (the S&P 500/400/600
    are mutually exclusive by construction), so the first index that lists it wins and the collision
    is logged rather than silently resolved."""
    index_names = index_names or list(INDEX_SOURCES)
    frames, seen = [], set()
    for name in index_names:
        df = fetch_index_constituents(name)
        if df.empty:
            continue
        dupes = sorted(set(df["Symbol"]) & seen)
        if dupes:
            print(f"[universe] {name}: {len(dupes)} ticker(s) already claimed by an earlier index, "
                  f"keeping the first listing: {dupes[:10]}")
            df = df[~df["Symbol"].isin(seen)]
        seen |= set(df["Symbol"])
        frames.append(df)
        print(f"[universe] {name}: {len(df)} constituents ({df['size_bucket'].iloc[0]})")
    if not frames:
        out = pd.DataFrame(columns=CONSTITUENT_COLUMNS)
        out["size_bucket"] = pd.Series(dtype=str)
        return out
    return pd.concat(frames, ignore_index=True)


def fetch_sp500_constituents(cache_path=None, url=None, timeout=None):
    """Returns a DataFrame with columns Symbol, GICS Sector, GICS Sub-Industry. Tries the
    live source first and refreshes the cache on success; on any failure (network error,
    timeout, bad status), falls back to the cached copy; if neither is available, warns
    and returns an empty DataFrame rather than inventing constituents."""
    cache_path = _resolve_cache_path(cache_path)
    url = url or PARAMS["sp500_source_url"]
    timeout = timeout or PARAMS["sp500_fetch_timeout_sec"]
    columns = ["Symbol", "GICS Sector", "GICS Sub-Industry"]

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        from io import StringIO
        df = pd.read_csv(StringIO(resp.text))
        return df[columns]
    except Exception as e:
        print(f"[universe] WARNING: could not fetch S&P 500 constituent list ({e}); "
              f"falling back to cache at {cache_path}")
        if os.path.exists(cache_path):
            df = pd.read_csv(cache_path)
            return df[columns]
        print("[universe] WARNING: no cached S&P 500 list available either — "
              "adding zero new tickers this run (never inventing constituents).")
        return pd.DataFrame(columns=columns)


def assign_benchmark(sector, sub_industry, size_bucket="large"):
    """Returns (sector_label, benchmark_ticker).

    Large caps keep the sector ETF (semiconductor sub-industries override to SMH). Mid and small
    caps get a SIZE benchmark instead, because complete liquid sector ETF families exist only for
    large caps - there is no mid- or small-cap XL* equivalent. Measuring an $800M industrial against
    XLI would make its relative strength largely a size bet rather than a sector-relative one.

    The sector LABEL is still returned and still drives v0.3 sector-neutral ranking; only the
    benchmark used for relative-strength features changes. See config.SIZE_BUCKET_BENCHMARK for why
    this asymmetry does not confound the large-vs-small decay comparison."""
    if sub_industry in SEMICONDUCTOR_SUB_INDUSTRIES:
        label = "Semiconductors"
    else:
        label = sector
    if size_bucket in SIZE_BENCHMARKED_BUCKETS:
        return label, SIZE_BUCKET_BENCHMARK[size_bucket]
    if sub_industry in SEMICONDUCTOR_SUB_INDUSTRIES:
        return label, "SMH"
    return label, SECTOR_BENCHMARK_MAP.get(sector, "SPY")


def build_universe_watchlist(existing_watchlist_df, constituents_df):
    """Appends any constituent not already present, plus any benchmark ETF not yet its own row.

    Existing rows are returned unchanged byte-for-byte and calling this on its own output adds zero
    rows (idempotent). `size_bucket` is backfilled as "large" for pre-existing rows: everything in
    the watchlist before v0.5 came from the S&P 500, so that is a statement of fact rather than a
    default. ETF rows carry no bucket - they are benchmarks, not holdings."""
    existing = existing_watchlist_df.copy()
    if "size_bucket" not in existing.columns:
        existing["size_bucket"] = "large"
    existing_tickers = set(existing["ticker"])
    has_bucket = "size_bucket" in constituents_df.columns
    has_source = "source_index" in constituents_df.columns
    new_rows = []

    for _, row in constituents_df.iterrows():
        # The source lists use the share-class dot convention (e.g. "BRK.B"); Yahoo/yfinance requires
        # a dash ("BRK-B") or the ticker fails to resolve every time, not just on a transient
        # rate-limit retry. Normalize here so the watchlist stores what data.py can actually fetch.
        ticker = str(row["Symbol"]).replace(".", "-")
        if ticker in existing_tickers:
            continue
        bucket = row["size_bucket"] if has_bucket else "large"
        source = row["source_index"] if has_source else "sp500"
        sector, benchmark = assign_benchmark(row["GICS Sector"], row["GICS Sub-Industry"], bucket)
        new_rows.append({"ticker": ticker, "sector": sector, "benchmark": benchmark,
                         "size_bucket": bucket, "notes": f"{source}_auto"})
        existing_tickers.add(ticker)

    merged = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) if new_rows         else existing

    benchmarks_needed = set(merged["benchmark"]) | {"SPY"}
    present_tickers = set(merged["ticker"])
    etf_rows = []
    for etf in sorted(benchmarks_needed):
        if etf not in present_tickers:
            etf_rows.append({"ticker": etf, "sector": "Index", "benchmark": "SPY",
                             "size_bucket": "", "notes": "benchmark"})
            present_tickers.add(etf)

    if etf_rows:
        merged = pd.concat([merged, pd.DataFrame(etf_rows)], ignore_index=True)

    return merged
