"""SEC Form 3/4/5 insider transactions — ingest and point-in-time aggregation.

A genuinely new information class, and the cheapest one available: it is free, it is perfectly
dated, and it reuses the `filed_date <= D` discipline already built for EDGAR fundamentals.

## Why the bulk datasets and not the filings themselves

SEC publishes a QUARTERLY structured dataset containing every ownership filing already parsed into
TSVs. Nine downloads (~94 MB) cover this project's entire price history. Enumerating the same
filings through the submissions API would be roughly 200,000 HTTP requests against an 8/s throttle —
days of wall clock for identical data.

## The two correctness rules

1. **`filed_date`, never `trans_date`.** An insider has two business days to report. Gating on the
   transaction date hands the model up to several days of foresight per filing — a textbook
   lookahead leak that would produce a beautiful, false result rather than an error. Every read goes
   through `storage.load_insider_transactions(filed_on_or_before=D)`, and
   `tests/test_insider.py::test_a_filing_is_invisible_until_its_filing_date` asserts it.

2. **Compensation is not an opinion.** Most insider "acquisitions" are grants (code A), option
   exercises (M), or shares withheld to pay tax on a grant (F). None reflect a view on the price.
   Only code **P** — an open-market purchase with the insider's own money — carries the documented
   anomaly. Lumping all acquisitions together buries that signal under an order of magnitude more
   payroll noise, so the codes are split at ingest and again at aggregation.

## The known coverage gap, stated up front

SEC publishes these datasets on a lag. Verified 2026-09-10: 2024Q1 through 2026Q1 exist; 2026Q2 and
2026Q3 return 404. So the store ends at 2026-03-31 while price history runs to 2026-09-08. A date
past the end of coverage returns **unknown**, never "no insider activity" — an absence of data is
not a zero (CLAUDE.md invariant #2). `insider_features_as_of` enforces this and every caller must
handle the `coverage_missing` flag.
"""

import csv
import io
import os
import time
import zipfile
from bisect import bisect_left, bisect_right
from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta, timezone

import requests

from src import storage
from src.config import (EDGAR, INSIDER, INSIDER_PURCHASE_CODES, INSIDER_TRANS_CODES)

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_sec_date(value):
    """SEC's datasets use `31-MAR-2025`. Returns ISO `2025-03-31`, or None.

    Returns None rather than guessing on anything unrecognized. A mis-parsed FILING_DATE would
    silently shift the point-in-time gate, which is the one error in this module that cannot be
    seen in the output."""
    if not value:
        return None
    parts = str(value).strip().split("-")
    if len(parts) != 3:
        return None
    day, mon, year = parts
    month = _MONTHS.get(mon.upper()[:3])
    if month is None:
        return None
    try:
        return date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def quarters_in_range(first=None, last=None):
    """[(year, quarter), ...] inclusive. Pure function of config, so it is testable without SEC."""
    first = first or INSIDER["first_quarter"]
    last = last or INSIDER["last_quarter"]
    out, cur = [], first
    while cur <= last:
        out.append(cur)
        y, q = cur
        cur = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


# ---------------------------------------------------------------------------
# Download (cached on disk — a re-run re-parses, never re-downloads)
# ---------------------------------------------------------------------------

def _cache_dir():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        *INSIDER["cache_dir"].split("/"))
    os.makedirs(path, exist_ok=True)
    return path


def download_quarter(year, quarter, cache_dir=None):
    """Fetch one quarterly zip, or return the cached copy. None if SEC has not published it yet.

    Caching is not just politeness to SEC: these datasets are REVISED, so a cached zip is also the
    only way a past analysis stays reproducible."""
    cache_dir = cache_dir or _cache_dir()
    name = "%dq%d_form345.zip" % (year, quarter)
    path = os.path.join(cache_dir, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    url = INSIDER["dataset_url"].format(year=year, quarter=quarter)
    headers = {"User-Agent": EDGAR["user_agent"], "Accept-Encoding": "gzip, deflate"}
    for attempt in range(INSIDER["max_retries"]):
        try:
            resp = requests.get(url, headers=headers, timeout=INSIDER["request_timeout_sec"])
            if resp.status_code == 404:
                # Not an error: SEC publishes on a lag, so the current quarter legitimately does not
                # exist yet. The caller records the gap rather than filling it.
                print("[insider] %dQ%d not published yet (404)" % (year, quarter))
                return None
            resp.raise_for_status()
            with open(path, "wb") as fh:
                fh.write(resp.content)
            print("[insider] downloaded %s (%.1f MB)" % (name, len(resp.content) / 1e6))
            return path
        except Exception as exc:
            wait = INSIDER["backoff_base_sec"] * (2 ** attempt)
            print("[insider] GET %s failed (%s), retry %d/%d in %.1fs"
                  % (url, exc, attempt + 1, INSIDER["max_retries"], wait))
            time.sleep(wait)
    print("[insider] gave up on %dQ%d" % (year, quarter))
    return None


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def _read_tsv(zf, name):
    """Yield dict rows from a TSV inside the zip. Streamed, not loaded — NONDERIV_TRANS alone is
    11 MB of text per quarter and there are nine quarters."""
    with zf.open(name) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
        for row in csv.DictReader(text, delimiter="\t"):
            yield row


def _relationship_flags(relationship_text):
    """SEC joins roles with commas: 'Director,Officer,TenPercentOwner'. Returns (dir, off, ten, other)."""
    parts = {p.strip().lower() for p in (relationship_text or "").split(",") if p.strip()}
    is_dir = "director" in parts
    is_off = "officer" in parts
    is_ten = "tenpercentowner" in parts
    return is_dir, is_off, is_ten, bool(parts - {"director", "officer", "tenpercentowner"})


def parse_quarter(zip_path, cik_filter=None, ticker_by_cik=None):
    """Parse one quarterly zip into insider transaction rows for the universe.

    `cik_filter` is a set of 10-digit zero-padded CIKs. Without it every US public company is
    ingested (~10,000 issuers), which is 5x the data for no benefit — this project scores 1,527
    names and cannot act on the rest.

    `ticker_by_cik` maps a CIK to OUR ticker. SEC's own ISSUERTRADINGSYMBOL is free text typed by
    the filer and arrives as "(CALX)", "-", "BFA, BFB", "BRK.A" — joining on it returned zero
    insider rows for 35 of our names whose filings were present the whole time. It is stored as
    `sec_symbol` for audit and never used as a key."""
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        # Pass 1: submissions -> the point-in-time metadata, filtered to our universe immediately so
        # the two large transaction files are only scanned for accessions we will actually keep.
        subs = {}
        for r in _read_tsv(zf, "SUBMISSION.tsv"):
            cik = (r.get("ISSUERCIK") or "").strip().zfill(10)
            if cik_filter is not None and cik not in cik_filter:
                continue
            filed = parse_sec_date(r.get("FILING_DATE"))
            if not filed:
                continue     # no usable point-in-time date -> the row cannot be gated -> drop it
            sec_symbol = (r.get("ISSUERTRADINGSYMBOL") or "").strip().upper() or None
            subs[r["ACCESSION_NUMBER"]] = {
                "cik": cik,
                "ticker": (ticker_by_cik or {}).get(cik),
                "sec_symbol": sec_symbol,
                "filed_date": filed,
                "doc_type": (r.get("DOCUMENT_TYPE") or "").strip(),
                "is_10b5_1": 1 if (r.get("AFF10B5ONE") or "").strip() in ("1", "true", "TRUE") else 0,
            }
        if not subs:
            return []

        # Pass 2: owners, COLLAPSED to one record per accession. A filing with several co-reporting
        # owners describes ONE economic transaction; keeping a row per owner would multiply its
        # share count by up to 10x in any aggregate.
        owners = defaultdict(lambda: {"ciks": [], "names": [], "titles": [], "rels": set(),
                                      "is_director": 0, "is_officer": 0, "is_ten_pct_owner": 0})
        for r in _read_tsv(zf, "REPORTINGOWNER.tsv"):
            acc = r.get("ACCESSION_NUMBER")
            if acc not in subs:
                continue
            o = owners[acc]
            o["ciks"].append((r.get("RPTOWNERCIK") or "").strip())
            o["names"].append((r.get("RPTOWNERNAME") or "").strip())
            if (r.get("RPTOWNER_TITLE") or "").strip():
                o["titles"].append(r["RPTOWNER_TITLE"].strip())
            rel = (r.get("RPTOWNER_RELATIONSHIP") or "").strip()
            if rel:
                o["rels"].add(rel)
            is_dir, is_off, is_ten, _ = _relationship_flags(rel)
            o["is_director"] |= int(is_dir)
            o["is_officer"] |= int(is_off)
            o["is_ten_pct_owner"] |= int(is_ten)

        # Pass 3: the transactions themselves, non-derivative and derivative kept side by side.
        # The raw store stays WIDE for the same reason `edgar_facts` does: a new factor should be a
        # query change, not a re-ingest.
        for table_kind, fname, sk_col in (("nonderiv", "NONDERIV_TRANS.tsv", "NONDERIV_TRANS_SK"),
                                          ("deriv", "DERIV_TRANS.tsv", "DERIV_TRANS_SK")):
            for r in _read_tsv(zf, fname):
                acc = r.get("ACCESSION_NUMBER")
                sub = subs.get(acc)
                if sub is None:
                    continue
                shares = _num(r.get("TRANS_SHARES"))
                price = _num(r.get("TRANS_PRICEPERSHARE"))
                o = owners.get(acc)
                rows.append({
                    "accession": acc,
                    "trans_sk": (r.get(sk_col) or "").strip(),
                    "table_kind": table_kind,
                    "cik": sub["cik"],
                    "ticker": sub["ticker"],
                    "sec_symbol": sub["sec_symbol"],
                    "filed_date": sub["filed_date"],
                    "trans_date": parse_sec_date(r.get("TRANS_DATE")),
                    "doc_type": sub["doc_type"],
                    "trans_code": (r.get("TRANS_CODE") or "").strip().upper() or None,
                    "acquired_disposed": (r.get("TRANS_ACQUIRED_DISP_CD") or "").strip().upper() or None,
                    "shares": shares,
                    "price_per_share": price,
                    # Left NULL when either leg is missing rather than defaulted to 0 — a
                    # zero-dollar transaction and an unpriced one are different facts.
                    "value_usd": (shares * price) if (shares is not None and price is not None) else None,
                    "shares_owned_after": _num(r.get("SHRS_OWND_FOLWNG_TRANS")),
                    "owner_cik": ",".join(o["ciks"]) if o else None,
                    "owner_name": " | ".join(o["names"])[:300] if o else None,
                    "relationship": ",".join(sorted(o["rels"])) if o else None,
                    "owner_title": " | ".join(o["titles"])[:200] if o else None,
                    "is_director": o["is_director"] if o else 0,
                    "is_officer": o["is_officer"] if o else 0,
                    "is_ten_pct_owner": o["is_ten_pct_owner"] if o else 0,
                    "is_10b5_1": sub["is_10b5_1"],
                    "direct_indirect": (r.get("DIRECT_INDIRECT_OWNERSHIP") or "").strip() or None,
                    "ingested_at": _now_iso(),
                })
    return rows


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

def ingest_insider_quarters(db_path=storage.DEFAULT_DB_PATH, first=None, last=None,
                            cik_filter=None, ticker_by_cik=None):
    """Download (or reuse), parse and store every quarter in range. Idempotent per quarter."""
    storage.init_db(db_path)
    if ticker_by_cik is None:
        ticker_by_cik = {str(v["cik"]).zfill(10): t
                         for t, v in storage.load_cik_map(db_path=db_path).items()
                         if v.get("cik") and not v.get("is_etf")}
    if cik_filter is None:
        cik_map = storage.load_cik_map(db_path=db_path)   # {ticker -> {cik, is_etf, ...}}
        cik_filter = {str(r["cik"]).zfill(10) for r in cik_map.values()
                      if r.get("cik") and not r.get("is_etf")}
        # A silent empty filter would ingest every US public company — 5x the rows for no benefit.
        # Fail loudly instead; an empty CIK map means EDGAR ingest has not run.
        if not cik_filter:
            raise RuntimeError(
                "cik_map is empty — run the EDGAR ingest first. Refusing to fall back to 'ingest "
                "every issuer', which would look like success and quietly 5x the store.")
    print("[insider] universe filter: %d CIKs" % len(cik_filter))

    summary = {"quarters": [], "rows": 0, "missing_quarters": []}
    for year, quarter in quarters_in_range(first, last):
        path = download_quarter(year, quarter)
        if path is None:
            summary["missing_quarters"].append("%dQ%d" % (year, quarter))
            continue
        rows = parse_quarter(path, cik_filter=cik_filter, ticker_by_cik=ticker_by_cik)
        written = storage.upsert_insider_transactions(rows, db_path=db_path)
        summary["quarters"].append({"quarter": "%dQ%d" % (year, quarter), "rows": written})
        summary["rows"] += written
        print("[insider] %dQ%d -> %d rows" % (year, quarter, written))

    coverage = storage.insider_coverage(db_path=db_path)
    summary["coverage"] = coverage
    print("[insider] store now holds %d rows, %d tickers, filed %s .. %s"
          % (coverage["n_rows"], coverage["n_tickers"],
             coverage["first_filed_date"], coverage["last_filed_date"]))
    if summary["missing_quarters"]:
        print("[insider] NOT PUBLISHED BY SEC: %s — dates after %s return UNKNOWN, never zero"
              % (", ".join(summary["missing_quarters"]), coverage["last_filed_date"]))
    return summary


# ---------------------------------------------------------------------------
# Point-in-time features
# ---------------------------------------------------------------------------

def _dedup_key(row):
    """Identity of an ECONOMIC transaction, independent of who filed it.

    Affiliated entities file separately for the same trade (two Apollo entities reporting the same
    1,185,242-share disposition of TBLA in 2025Q1, under different accession numbers). Summing
    across accessions would count it twice. Deduplicating on the trade's own attributes is the only
    way to net that out — the accession number cannot, by construction."""
    return (row.get("cik"), row.get("trans_date"), row.get("trans_code"),
            row.get("shares"), row.get("price_per_share"))


def _empty_features(window_days):
    w = window_days
    return {
        "insider_buy_count_%dd" % w: None,
        "insider_sell_count_%dd" % w: None,
        "insider_net_buy_value_%dd" % w: None,
        "insider_buy_value_%dd" % w: None,
        "insider_buyer_count_%dd" % w: None,
        "insider_officer_buy_count_%dd" % w: None,
        "insider_buy_minus_sell_count_%dd" % w: None,
        "days_since_insider_buy": None,
        "coverage_missing": False,
    }


def _aggregate(rows, as_of_date, window_days):
    """THE aggregation. Both the per-ticker accessor and the bulk index call this and nothing else,
    so a second, subtly-different definition of "insider buying" cannot drift into existence — the
    same discipline `evaluation.trading_calendar` exists for.

    `rows` must already be filtered to the window and to filed_date <= as_of_date."""
    out = _empty_features(window_days)
    seen, buys, sells = set(), [], []
    for r in rows:
        if r.get("table_kind") != "nonderiv":
            continue        # derivative legs are option mechanics, not share purchases
        key = _dedup_key(r)
        if key in seen:
            continue
        seen.add(key)
        code = r.get("trans_code")
        if code in INSIDER_PURCHASE_CODES:
            buys.append(r)
        elif code == "S":
            sells.append(r)

    buy_value = sum(r["value_usd"] or 0.0 for r in buys)
    sell_value = sum(r["value_usd"] or 0.0 for r in sells)
    w = window_days
    out["insider_buy_count_%dd" % w] = len(buys)
    out["insider_sell_count_%dd" % w] = len(sells)
    out["insider_buy_value_%dd" % w] = buy_value
    out["insider_net_buy_value_%dd" % w] = buy_value - sell_value
    out["insider_buy_minus_sell_count_%dd" % w] = len(buys) - len(sells)
    out["insider_buyer_count_%dd" % w] = len({r.get("owner_cik") for r in buys})
    out["insider_officer_buy_count_%dd" % w] = sum(1 for r in buys if r.get("is_officer"))
    if buys:
        latest = max(r["filed_date"] for r in buys)
        out["days_since_insider_buy"] = (date.fromisoformat(as_of_date)
                                         - date.fromisoformat(latest)).days
    return out


def insider_features_as_of(ticker, as_of_date, window_days=90, db_path=storage.DEFAULT_DB_PATH,
                           coverage_end=None, rows=None):
    """Insider aggregates for one ticker as known on `as_of_date`. REPORT-ONLY for now.

    Returns a dict whose every value is None when the date lies past the end of ingested coverage,
    plus `coverage_missing=True`. That distinction is the entire point: a stretch with no filings and
    a stretch with no DATA look identical once they are both written as 0, and one of them is a lie.
    """
    coverage_end = coverage_end or storage.insider_coverage(db_path=db_path)["last_filed_date"]
    start = (date.fromisoformat(as_of_date) - timedelta(days=window_days)).isoformat()
    if not coverage_end or as_of_date > coverage_end:
        out = _empty_features(window_days)
        out["coverage_missing"] = True
        return out
    if rows is None:
        rows = storage.load_insider_transactions(
            ticker=ticker, filed_on_or_before=as_of_date, filed_on_or_after=start, db_path=db_path)
    else:
        rows = [r for r in rows if start <= r["filed_date"] <= as_of_date]
    return _aggregate(rows, as_of_date, window_days)


# ---------------------------------------------------------------------------
# Bulk index — the same arithmetic, fast enough for a 440-date x 1,500-name panel
# ---------------------------------------------------------------------------

InsiderIndex = namedtuple("InsiderIndex", "by_ticker coverage_end coverage_start")


def build_insider_index(db_path=storage.DEFAULT_DB_PATH, codes=("P", "S")):
    """Load every informative transaction ONCE, grouped by ticker with filed_dates pre-sorted.

    The same lesson as `edgar.build_facts_index`: one query per (ticker, date) turned a backfill
    into a 26-hour job. Here it would be ~660,000 queries. Only codes P and S are loaded — the
    compensation codes are 25x more numerous and contribute nothing to any aggregate."""
    rows = storage.load_insider_transactions(codes=list(codes), db_path=db_path)
    by_ticker = defaultdict(list)
    for r in rows:
        if r.get("ticker") and r.get("table_kind") == "nonderiv":
            by_ticker[r["ticker"]].append(r)
    for t in by_ticker:
        by_ticker[t].sort(key=lambda r: r["filed_date"])
    cov = storage.insider_coverage(db_path=db_path)
    return InsiderIndex(by_ticker=dict(by_ticker), coverage_end=cov["last_filed_date"],
                        coverage_start=cov["first_filed_date"])


def features_from_index(index, ticker, as_of_date, window_days=90):
    """The bulk path. Identical arithmetic to `insider_features_as_of` — both call `_aggregate`."""
    if not index.coverage_end or as_of_date > index.coverage_end:
        out = _empty_features(window_days)
        out["coverage_missing"] = True
        return out
    rows = index.by_ticker.get(ticker, ())
    start = (date.fromisoformat(as_of_date) - timedelta(days=window_days)).isoformat()
    dates = [r["filed_date"] for r in rows]
    lo = bisect_left(dates, start)
    hi = bisect_right(dates, as_of_date)
    return _aggregate(rows[lo:hi], as_of_date, window_days)


INSIDER_FEATURE_COLUMNS = [
    "insider_buy_count_90d", "insider_sell_count_90d", "insider_buy_value_90d",
    "insider_net_buy_value_90d", "insider_buy_minus_sell_count_90d",
    "insider_buyer_count_90d", "insider_officer_buy_count_90d", "days_since_insider_buy",
]
