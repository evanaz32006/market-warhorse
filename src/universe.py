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


# ---------------------------------------------------------------------------
# POINT-IN-TIME index membership — the survivorship measurement
# ---------------------------------------------------------------------------

# The universe here is TODAY's S&P 1500 projected backwards to 2024-06. That inflates exactly the
# kind of strategy this project ranks: survivors are, by construction, the names that trended. Every
# output row is stamped `survivorship_biased=True` and the magnitude has never been quantified, so
# the one positive result (+10.4% at 120d) is an upper bound rather than an estimate.
#
# The honest fix needs to know WHO WAS ACTUALLY IN THE INDEX on date D, including names dropped
# before the watchlist was built — those are the ones missing from the sample, and they are missing
# precisely because they did badly.
#
# A previous attempt parsed Wikipedia's "Selected changes" table and failed; that table is no longer
# on the page at all (verified 2026-09-16: the article now renders exactly two tables, the
# constituents and a navbox). So this does not reconstruct membership from a change log. It reads
# the LIST AS IT STOOD, from Wikipedia's own revision history via the MediaWiki API, which is both
# simpler and closer to the truth — no replaying of adds and drops, no missed edit compounding
# forward.

MEMBERSHIP_CACHE = "data/index_membership_history.csv"

MEMBERSHIP_TITLES = {
    "sp500": "List of S&P 500 companies",
    "sp400": "List of S&P 400 companies",
    "sp600": "List of S&P 600 companies",
}

_WIKI_API = "https://en.wikipedia.org/w/api.php"

MEMBERSHIP_COLUMNS = ["index_name", "as_of_date", "revision_id", "revision_date", "ticker",
                      "date_added", "sector"]


def _wiki_headers():
    """Wikipedia asks for a descriptive User-Agent with a contact, exactly as SEC does."""
    from src.config import SEC_CONTACT_EMAIL
    contact = SEC_CONTACT_EMAIL or "unknown"
    return {"User-Agent": "market-warhorse research (contact: %s)" % contact}


def _normalize_symbol(sym):
    """Wikipedia writes share classes with a dot (BRK.B); our watchlist and Yahoo use a dash."""
    return str(sym).strip().upper().replace(".", "-")


def revision_before(title, as_of_date, timeout=None):
    """(revid, revision_date) of the newest revision of `title` at or before as_of_date.

    `rvdir=older` from as_of_date is the no-lookahead gate at the API level: the revision returned
    cannot contain an edit made after that date."""
    timeout = timeout or PARAMS["index_fetch_timeout_sec"]
    resp = requests.get(_WIKI_API, params={
        "action": "query", "prop": "revisions", "titles": title, "rvlimit": 1,
        "rvstart": "%sT23:59:59Z" % as_of_date, "rvdir": "older",
        "rvprop": "ids|timestamp", "format": "json"}, headers=_wiki_headers(), timeout=timeout)
    resp.raise_for_status()
    page = next(iter(resp.json()["query"]["pages"].values()))
    revs = page.get("revisions") or []
    if not revs:
        return None, None
    return revs[0]["revid"], revs[0]["timestamp"][:10]


def constituents_at_revision(revid, as_of_date=None, timeout=None):
    """The constituent table from one specific revision, as {ticker: {...}}.

    `as_of_date` guards a REAL lookahead hazard that the revision date alone does not. S&P announces
    index changes roughly a week BEFORE they take effect, and Wikipedia editors routinely add the
    incoming company immediately — carrying a FUTURE "Date added". So a revision dated D can
    legitimately list a company that did not join until D+5, and counting it as a member on D is
    lookahead by the back door.

    When a "Date added" is present and parses, a row is admitted only if that date is <= as_of_date.
    A missing or unparseable date admits the row: those are long-standing members, and dropping them
    over a formatting quirk would silently shrink the universe."""
    timeout = timeout or PARAMS["index_fetch_timeout_sec"] * 2
    resp = requests.get(_WIKI_API, params={"action": "parse", "oldid": revid, "prop": "text",
                                           "format": "json"},
                        headers=_wiki_headers(), timeout=timeout)
    resp.raise_for_status()
    html = resp.json()["parse"]["text"]["*"]
    table = _pick_constituents_table(pd.read_html(StringIO(html)))
    if table is None:
        return {}

    added_col = next((c for c in table.columns if "date added" in str(c).strip().lower()), None)
    sector_col = next((c for c in table.columns if "gics sector" in str(c).strip().lower()), None)
    out, not_yet_effective = {}, []
    for _, row in table.iterrows():
        ticker = _normalize_symbol(row["Symbol"])
        if not ticker or ticker == "NAN":
            continue
        added = None
        if added_col is not None:
            # `errors="coerce"` + an explicit NaT check, NOT a try/except. pd.to_datetime does not
            # RAISE on "n/a" — it returns NaT, whose str() is "NaT", which compares GREATER than any
            # ISO date. So the obvious version silently classified every unparseable row as
            # "announced but not yet effective" and dropped long-standing members from the universe.
            parsed = pd.to_datetime(str(row[added_col])[:10], errors="coerce")
            if not pd.isna(parsed):
                added = parsed.date().isoformat()
        if as_of_date and added and added > as_of_date:
            not_yet_effective.append((ticker, added))
            continue
        out[ticker] = {"ticker": ticker, "date_added": added,
                       "sector": str(row[sector_col]) if sector_col is not None else None}
    if not_yet_effective:
        print("[universe] rev %s: excluded %d name(s) listed but not yet effective on %s: %s"
              % (revid, len(not_yet_effective), as_of_date, not_yet_effective[:5]))
    return out


def load_membership_cache(cache_path=None):
    """The accumulated membership history as a DataFrame, or an empty one.

    A CSV rather than the database, deliberately: this is research input for ONE question, and
    nothing in the nightly pipeline should be able to consume it by accident."""
    path = _resolve_cache_path(cache_path or MEMBERSHIP_CACHE)
    if not os.path.exists(path):
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    return pd.read_csv(path, dtype=str).reindex(columns=MEMBERSHIP_COLUMNS)


def build_membership_history(index_names, dates, cache_path=None, sleep_sec=0.4):
    """Fetch and CACHE point-in-time membership for each (index, date), skipping pairs already held.

    Resumable and append-only for the same reason the EDGAR ingest is: a re-run must never re-pay
    for what it already has, nor overwrite it. A failure on one date is logged and skipped — a
    partial history is honest, an invented one is not."""
    import time
    path = _resolve_cache_path(cache_path or MEMBERSHIP_CACHE)
    existing = load_membership_cache(path)
    have = set(zip(existing["index_name"], existing["as_of_date"])) if not existing.empty else set()

    new_rows = []
    for index_name in index_names:
        title = MEMBERSHIP_TITLES[index_name]
        for d in dates:
            if (index_name, d) in have:
                continue
            try:
                revid, rev_date = revision_before(title, d)
                if revid is None:
                    print("[universe] %s %s: no revision that early — skipped" % (index_name, d))
                    continue
                members = constituents_at_revision(revid, as_of_date=d)
            except Exception as e:
                print("[universe] %s %s: fetch/parse failed (%s) — skipped, nothing invented"
                      % (index_name, d, e))
                continue
            if not members:
                print("[universe] %s %s: rev %s held no constituent table — skipped"
                      % (index_name, d, revid))
                continue
            for t, meta in members.items():
                new_rows.append({"index_name": index_name, "as_of_date": d, "revision_id": revid,
                                 "revision_date": rev_date, "ticker": t,
                                 "date_added": meta["date_added"], "sector": meta["sector"]})
            print("[universe] %s %s: %d members (rev %s of %s)"
                  % (index_name, d, len(members), revid, rev_date), flush=True)
            time.sleep(sleep_sec)

    if new_rows:
        out = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out.to_csv(path, index=False)
        print("[universe] membership cache: +%d rows -> %s" % (len(new_rows), path))
        return out
    return existing


def members_as_of(cache, index_name, as_of_date):
    """The membership snapshot in `cache` whose as_of_date is the newest at or before as_of_date.

    Never a later snapshot: that would put a company in the index before it joined, which is the
    same lookahead the whole project exists to refuse."""
    if cache is None or cache.empty:
        return set()
    sub = cache[(cache["index_name"] == index_name) & (cache["as_of_date"] <= as_of_date)]
    if sub.empty:
        return set()
    newest = sub["as_of_date"].max()
    return set(sub[sub["as_of_date"] == newest]["ticker"])


def all_members_ever(cache, index_names=None):
    """Every ticker that appears in ANY cached snapshot. The difference between this and today's
    watchlist is the survivorship hole: names that were in the index while we were tracking, and
    were dropped before the watchlist was built, so they were never scored even once."""
    if cache is None or cache.empty:
        return set()
    sub = cache if index_names is None else cache[cache["index_name"].isin(index_names)]
    return set(sub["ticker"].dropna())
