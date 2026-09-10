"""SEC filing index — 8-K material events, 10-K/10-Q dates. Ingest and point-in-time features.

## Why the submissions API rather than the quarterly bulk index

`https://data.sec.gov/submissions/CIK{cik10}.json` returns, per company, every filing with its form
type, filing date, **acceptance timestamp**, and — for 8-Ks — the **item codes**. The quarterly
`form.idx` bulk files list filings but carry no item codes, and the item code is where the entire
signal lives: a 5.07 (annual-meeting vote) and a 4.02 (previously issued financials can no longer be
relied upon) are both "an 8-K", and only one of them matters.

Cost is 1,502 requests at 8/s — about three minutes. Cheap enough that the stored form list is
deliberately NARROW (see `FILING_FORMS`): unlike `edgar_facts`, where a re-ingest is 15 minutes and
the store is kept wide so a new factor is a config change, here a re-ingest is three minutes and
disk is the scarcer resource.

## Two correctness rules

1. **`acceptanceDateTime`, not just `filingDate`.** An 8-K accepted at 16:35 ET on Tuesday is
   stamped with Tuesday's date but could not be traded until Wednesday — the market was closed. A
   feature that treats it as knowable at Tuesday's close is reading a headline before it was
   published. `effective_date` rolls any filing accepted at or after the close to the NEXT trading
   session, and rolls weekend/holiday filings forward too.

2. **Routine is not material.** Item 9.01 is "financial statements and exhibits" — an attachment
   notice bolted onto most other items. Item 5.07 is the annual shareholder vote. Counting those as
   material events is the same mistake as counting an option grant as insider buying: it buries a
   real signal under an order of magnitude of paperwork.

Unlike the Form 4 bulk datasets, this source is CURRENT — it returns filings through today — so a
feature built on it could serve a nightly run without a second pipeline.
"""

import json
import os
import time
from bisect import bisect_left, bisect_right
from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta, timezone

import requests

from src import storage
from src.config import (EDGAR, EVENT_8K_GROUPS, EVENT_8K_WINDOWS, FILING_FORMS,
                        MATERIAL_8K_ITEMS, ROUTINE_8K_ITEMS, SEC_SUBMISSIONS)

_last_request_ts = 0.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _throttle():
    """SEC's hard limit is 10 requests/s. Shared spacing, same discipline as edgar._throttle."""
    global _last_request_ts
    min_gap = 1.0 / EDGAR["max_requests_per_sec"]
    wait = min_gap - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def _get_json(url):
    """GET with the mandatory descriptive User-Agent, throttle and backoff. None on 404 or
    persistent failure — fail-soft, so one bad company is logged and skipped."""
    headers = {"User-Agent": EDGAR["user_agent"], "Accept-Encoding": "gzip, deflate"}
    for attempt in range(EDGAR["max_retries"]):
        _throttle()
        try:
            resp = requests.get(url, headers=headers, timeout=EDGAR["request_timeout_sec"])
            if resp.status_code == 404:
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError("status %d" % resp.status_code)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            wait = EDGAR["backoff_base_sec"] * (2 ** attempt)
            print("[filings] GET %s failed (%s), retry %d/%d in %.1fs"
                  % (url, exc, attempt + 1, EDGAR["max_retries"], wait))
            time.sleep(wait)
    print("[filings] gave up on %s" % url)
    return None


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

def _rows_from_block(block, cik, ticker, forms, since):
    """One `filings.recent` (or older-chunk) block -> rows, filtered to `forms` and `since`."""
    out = []
    n = len(block.get("accessionNumber", []))
    for i in range(n):
        form = (block["form"][i] or "").strip()
        if forms and form not in forms:
            continue
        filed = (block["filingDate"][i] or "").strip()
        if not filed or (since and filed < since):
            continue
        out.append({
            "accession": block["accessionNumber"][i],
            "cik": cik,
            "ticker": ticker,
            "form": form,
            "filed_date": filed,
            # ISO-8601 with a -04:00/-05:00 offset, e.g. 2026-07-30T16:30:37.000-04:00. Kept
            # VERBATIM rather than converted: the trading-calendar roll happens at read time, so a
            # calendar correction never leaves stale derived dates behind in the store.
            "acceptance_datetime": (block.get("acceptanceDateTime") or [None] * n)[i],
            "report_date": (block.get("reportDate") or [None] * n)[i] or None,
            # Comma-separated 8-K item codes ("2.02,9.01"). Empty for non-8-K forms.
            "items": ((block.get("items") or [None] * n)[i] or "").strip() or None,
            "primary_doc": (block.get("primaryDocument") or [None] * n)[i] or None,
            "ingested_at": _now_iso(),
        })
    return out


def fetch_company_filings(cik, ticker=None, forms=None, since=None):
    """Every filing of the requested forms for one company, following older-chunk files if needed.

    `filings.recent` holds only the most recent ~1,000 filings of ALL types. A heavy Form 4 filer
    can burn that budget in under two years, so if the block does not reach back to `since` the
    older chunks are followed. Skipping that would silently truncate history for exactly the most
    active companies — a coverage hole correlated with company size, which is the worst kind."""
    forms = set(forms or FILING_FORMS)
    cik10 = str(cik).zfill(10)
    blob = _get_json(SEC_SUBMISSIONS["submissions_url"].format(cik10=cik10))
    if not blob:
        return []
    filings = blob.get("filings") or {}
    recent = filings.get("recent") or {}
    rows = _rows_from_block(recent, cik10, ticker, forms, since)

    dates = recent.get("filingDate") or []
    oldest_in_recent = dates[-1] if dates else None
    if since and oldest_in_recent and oldest_in_recent > since:
        for chunk in (filings.get("files") or []):
            if chunk.get("filingTo") and chunk["filingTo"] < since:
                continue      # entirely before our window
            extra = _get_json(SEC_SUBMISSIONS["archive_url"].format(name=chunk["name"]))
            if extra:
                rows.extend(_rows_from_block(extra, cik10, ticker, forms, since))
    return rows


def ingest_filings(db_path=storage.DEFAULT_DB_PATH, since=None, forms=None, tickers=None):
    """Fetch and store the filing index for the whole universe. Idempotent per accession."""
    storage.init_db(db_path)
    since = since or SEC_SUBMISSIONS["since_date"]
    cik_map = storage.load_cik_map(db_path=db_path)
    targets = [(t, str(v["cik"]).zfill(10)) for t, v in sorted(cik_map.items())
               if v.get("cik") and not v.get("is_etf")
               and (tickers is None or t in set(tickers))]
    if not targets:
        raise RuntimeError(
            "cik_map is empty — run the EDGAR ingest first. Refusing to proceed, which would "
            "otherwise look like a successful run over zero companies.")

    print("[filings] %d companies, forms=%s, since=%s"
          % (len(targets), ",".join(sorted(forms or FILING_FORMS)), since))
    total, failed = 0, []
    for i, (ticker, cik) in enumerate(targets, 1):
        rows = fetch_company_filings(cik, ticker=ticker, forms=forms, since=since)
        if not rows:
            failed.append(ticker)
        total += storage.upsert_sec_filings(rows, db_path=db_path)
        if i % 200 == 0:
            print("[filings] %d/%d companies, %d rows" % (i, len(targets), total))
    # Written only after every company has been attempted. A run that dies partway leaves the
    # PREVIOUS marker in place, so features keep gating on the last date we can actually vouch for
    # rather than silently trusting a half-populated table.
    storage.set_meta(storage.SEC_FILINGS_INGEST_MARKER,
                     datetime.now(timezone.utc).date().isoformat(), db_path=db_path)
    cov = storage.sec_filings_coverage(db_path=db_path)
    print("[filings] stored %d rows | coverage %s .. %s | %d tickers | %d companies returned nothing"
          % (cov["n_rows"], cov["first_filed_date"], cov["last_filed_date"], cov["n_tickers"],
             len(failed)))
    if failed:
        print("[filings] no filings returned for: %s%s"
              % (", ".join(failed[:20]), " ..." if len(failed) > 20 else ""))
    return {"rows": total, "coverage": cov, "no_filings": failed}


# ---------------------------------------------------------------------------
# Point-in-time: when did the market actually learn this?
# ---------------------------------------------------------------------------

def effective_date(filed_date, acceptance_datetime, calendar, close_hour=None):
    """The first trading session on which a filing could have been acted on.

    An 8-K accepted at 16:35 ET on a Tuesday carries Tuesday's `filingDate`, but the market was
    already closed — treating it as knowable at Tuesday's close reads a headline before it was
    published. So a filing accepted at or after the close rolls to the NEXT session, and a filing on
    a non-trading day rolls forward to the next one.

    `calendar` is the master session list. Returns None if the roll lands past its end, which is the
    honest answer for a filing whose first tradeable session has not happened yet."""
    close_hour = close_hour if close_hour is not None else SEC_SUBMISSIONS["market_close_hour_et"]
    target = filed_date
    if acceptance_datetime:
        try:
            # SEC stamps these in Eastern time with an explicit offset, so the clock time in the
            # string is already the exchange's own clock — no timezone conversion needed, and none
            # is attempted (a wrong conversion here shifts the gate by a day and is invisible).
            stamp = str(acceptance_datetime)[:19]
            dt = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")
            if dt.hour >= close_hour:
                target = (dt.date() + timedelta(days=1)).isoformat()
            else:
                target = dt.date().isoformat()
        except (ValueError, TypeError):
            target = filed_date          # unparseable -> fall back, never guess a time
    i = bisect_left(calendar, target)
    return calendar[i] if i < len(calendar) else None


def parse_items(items):
    """"2.02,9.01" -> {"2.02", "9.01"}."""
    if not items:
        return set()
    return {p.strip() for p in str(items).split(",") if p.strip()}


def is_material(items):
    """True if the filing carries at least one item that is not pure paperwork.

    9.01 (financial statements and exhibits) is an attachment notice bolted onto most other items;
    5.07 is the annual shareholder vote. An 8-K carrying ONLY those is administrative. Counting it
    as a material event is the same error as counting an option grant as insider buying."""
    codes = parse_items(items)
    return bool(codes - ROUTINE_8K_ITEMS)


EventIndex = namedtuple("EventIndex", "by_ticker calendar coverage_start coverage_end")


def build_event_index(db_path=storage.DEFAULT_DB_PATH, calendar=None, forms=("8-K", "8-K/A")):
    """Load 8-K filings once, keyed by ticker with `effective_date` precomputed and sorted.

    Same lesson as `edgar.build_facts_index` and `insider.build_insider_index`: one query per
    (ticker, date) is what turned a backfill into a 26-hour job."""
    from src import evaluation
    calendar = list(calendar or evaluation.trading_calendar(db_path=db_path))
    rows = storage.load_sec_filings(forms=list(forms), db_path=db_path)
    by_ticker = defaultdict(list)
    for r in rows:
        if not r.get("ticker"):
            continue
        eff = effective_date(r["filed_date"], r.get("acceptance_datetime"), calendar)
        if eff is None:
            continue      # its first tradeable session has not happened yet
        by_ticker[r["ticker"]].append({
            "effective_date": eff, "filed_date": r["filed_date"], "items": r.get("items"),
            "material": is_material(r.get("items")), "form": r.get("form"),
        })
    for t in by_ticker:
        by_ticker[t].sort(key=lambda r: r["effective_date"])
    cov = storage.sec_filings_coverage(db_path=db_path)
    # `ingested_through` when a completed ingest has stamped one; otherwise fall back to the newest
    # filing present. The fallback keeps the module usable on a hand-built store (and in tests)
    # without weakening the production guarantee.
    coverage_end = cov.get("ingested_through") or cov["last_filed_date"]
    return EventIndex(by_ticker=dict(by_ticker), calendar=calendar,
                      coverage_start=cov["first_filed_date"], coverage_end=coverage_end)


def event_feature_columns(groups=None, windows=None):
    """The feature names this module produces. Derived from config so adding an item group is a
    config change, never an edit in three places."""
    groups = groups or EVENT_8K_GROUPS
    windows = windows or EVENT_8K_WINDOWS
    cols = ["%s_8k_%dd" % (g, w) for g in sorted(groups) for w in windows]
    return cols + ["days_since_material_8k", "days_since_earnings_8k"]


EVENT_FEATURE_COLUMNS = event_feature_columns()


def _matches(row, codes):
    """`codes=None` means "anything that is not pure paperwork"."""
    return row["material"] if codes is None else bool(parse_items(row["items"]) & codes)


def event_features_as_of(index, ticker, as_of_date, groups=None, windows=None):
    """8-K event aggregates for one ticker as known at the CLOSE of `as_of_date`.

    Every count uses `effective_date`, so a filing accepted after the close on `as_of_date` is not
    included — it was not actionable yet. Returns all-None with `coverage_missing=True` past the end
    of ingested coverage: an absence of data is not an absence of news (CLAUDE.md #2)."""
    groups = groups or EVENT_8K_GROUPS
    windows = windows or EVENT_8K_WINDOWS
    out = {c: None for c in event_feature_columns(groups, windows)}
    out["coverage_missing"] = False
    if not index.coverage_end or as_of_date > index.coverage_end:
        out["coverage_missing"] = True
        return out

    rows = index.by_ticker.get(ticker, [])
    dates = [r["effective_date"] for r in rows]
    hi = bisect_right(dates, as_of_date)          # strictly "known by the close of as_of_date"
    seen = rows[:hi]
    as_of = date.fromisoformat(as_of_date)

    for w in windows:
        start = (as_of - timedelta(days=w)).isoformat()
        window = seen[bisect_left(dates, start):hi]
        for g, codes in groups.items():
            out["%s_8k_%dd" % (g, w)] = sum(1 for r in window if _matches(r, codes))

    for name, codes in (("days_since_material_8k", None), ("days_since_earnings_8k", {"2.02"})):
        hits = [r for r in seen if _matches(r, codes)]
        if hits:
            out[name] = (as_of - date.fromisoformat(hits[-1]["effective_date"])).days
    return out
