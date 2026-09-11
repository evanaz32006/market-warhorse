"""SEC EDGAR point-in-time fundamentals (v0.4).

EDGAR publishes every XBRL fact a company has filed, each stamped with the date it was FILED. That
filed date is what makes legitimate point-in-time reconstruction possible: a fact is usable in a
snapshot for date D iff `filed_date <= D`. This module:

- Phase 1: maps universe tickers -> CIK, fetches per-company facts from EDGAR (throttled, fail-soft),
  and stores EVERY us-gaap/dei fact verbatim in `edgar_facts` (the "wide pipe" — future factors are a
  config change, not a re-ingest).
- Phase 2 (below): `get_fundamentals_as_of(ticker, date, price)` resolves those raw facts into the
  same ratio dict yfinance produced, strictly filed-date-gated, originally-filed (not restated).

SEC compliance: a descriptive User-Agent with a real contact on every request, and <= 10 req/s.
"""
import json
import os
import re
import time
from bisect import bisect_right
from datetime import date, datetime, timezone

import pandas as pd
import requests

from src import storage
from src.config import (EDGAR, EDGAR_CONCEPT_TAGS, EDGAR_DEBT_LEGS,
                        EDGAR_DEBT_TAGS_INCLUDING_LEASES, EDGAR_DEBT_TO_EQUITY_SCALE,
                        EDGAR_LEASE_LEGS,
                        EDGAR_EXCLUDED_FIELDS, EDGAR_FINANCIAL_SECTORS, ETF_SECTOR_LABEL, PARAMS)

# Concepts the EDGAR resolver derives that yfinance also provides — the Phase-3 comparison set.
_VALIDATION_CONCEPTS = ["trailing_pe", "price_to_sales", "price_to_book", "profit_margin",
                        "operating_margin", "return_on_equity", "debt_to_equity", "current_ratio"]

_last_request_ts = 0.0


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _num(v):
    """Coerce an XBRL fact value to float (stored as REAL). Returns None if non-numeric. Floats avoid
    the OverflowError SQLite raises when a Python int exceeds its 64-bit INTEGER range — some filers
    report values (public float, share counts) larger than 2**63; our concepts are all well within
    float's ~15-digit precision, so no meaningful loss."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _throttle():
    """Enforce <= EDGAR['max_requests_per_sec'] by spacing requests (SEC's hard limit is 10/s)."""
    global _last_request_ts
    min_gap = 1.0 / EDGAR["max_requests_per_sec"]
    wait = min_gap - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def _http_get_json(url):
    """GET url as JSON with the mandatory descriptive User-Agent, throttle, and retry/backoff. Returns
    the parsed object, or None on persistent failure (fail-soft — a bad company is logged and skipped,
    never crashes the ingest)."""
    headers = {"User-Agent": EDGAR["user_agent"], "Accept-Encoding": "gzip, deflate"}
    for attempt in range(EDGAR["max_retries"]):
        _throttle()
        try:
            resp = requests.get(url, headers=headers, timeout=EDGAR["request_timeout_sec"])
            if resp.status_code == 404:
                return None  # no such company facts — legitimate (e.g. foreign filer), not an error
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"status {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            sleep_for = EDGAR["backoff_base_sec"] * (2 ** attempt)
            print(f"[edgar] GET {url} failed ({e}), retry {attempt + 1}/{EDGAR['max_retries']} in {sleep_for:.1f}s")
            time.sleep(sleep_for)
    print(f"[edgar] GET {url} gave up after {EDGAR['max_retries']} attempts — skipped")
    return None


# ---------------------------------------------------------------------------
# Phase 1a — CIK <-> ticker mapping
# ---------------------------------------------------------------------------

def _norm_ticker(t):
    """Normalize a ticker for matching across EDGAR's conventions vs ours: uppercase, strip anything
    non-alphanumeric. So BRK-B / BRK.B / BRKB all collapse to BRKB (the share-class quirk that bit us)."""
    return re.sub(r"[^A-Z0-9]", "", str(t).upper())


def build_cik_map(tickers, sector_by_ticker, db_path=storage.DEFAULT_DB_PATH):
    """Fetch SEC's ticker->CIK table and map every universe ticker to a 10-digit zero-padded CIK.
    ETFs/benchmarks (sector == ETF_SECTOR_LABEL) carry no company fundamentals -> is_etf=1, no CIK.
    Every non-ETF ticker that fails to map is LOGGED (never silently dropped). Returns a summary dict."""
    storage.init_db(db_path)
    raw = _http_get_json(EDGAR["company_tickers_url"])
    by_exact, norm_owners = {}, {}
    if raw:
        for entry in raw.values():
            tkr, cik = entry.get("ticker"), entry.get("cik_str")
            if tkr and cik is not None:
                cik10 = f"{int(cik):010d}"
                by_exact.setdefault(str(tkr).upper(), cik10)
                norm_owners.setdefault(_norm_ticker(tkr), {})[str(tkr).upper()] = cik10
    else:
        print("[edgar] WARNING: could not fetch company_tickers.json — no tickers mapped this run")

    # Normalizing punctuation away is what lets BRK-B find BRKB — but it also makes PREFERRED-share
    # tickers collide with ordinary common stock. SEC lists "BC-PC" (Brunswick preferred series C),
    # which normalizes to BCPC and collided with Balchem; and "T-PC" (AT&T preferred C), which
    # normalized to TPC and collided with Tutor Perini. The old code assigned into a flat dict, so
    # whichever entry came last silently won, and BALCHEM WAS MAPPED TO BRUNSWICK'S CIK while TUTOR
    # PERINI WAS MAPPED TO AT&T'S.
    #
    # That produced no error and no wrong number — only because facts are READ BACK BY TICKER and
    # ingest is deduplicated by CIK, so the mis-mapped names simply ingested nothing and resolved to
    # NULL. A future "cleanup" that keys the read on CIK instead would have activated it instantly
    # and started scoring Balchem on Brunswick's financials. So: exact match wins, a normalized
    # match is used only when it is UNAMBIGUOUS, and an ambiguous one is refused and logged.
    by_norm = {k: next(iter(v.values())) for k, v in norm_owners.items()
               if len(set(v.values())) == 1}
    ambiguous = {k: v for k, v in norm_owners.items() if len(set(v.values())) > 1}

    rows, mapped, etfs, unmapped, collisions = [], 0, 0, [], []
    for t in tickers:
        is_etf = 1 if sector_by_ticker.get(t) == ETF_SECTOR_LABEL else 0
        if is_etf:
            etfs += 1
            rows.append({"ticker": t, "cik": None, "is_etf": 1, "mapped_ok": 0, "checked_at": _now_iso()})
            continue
        # Exact FIRST. Our "BCPC" is SEC's "BCPC" (Balchem) verbatim; only fall through to the
        # punctuation-insensitive match for genuine spelling differences like BRK-B vs BRKB.
        cik = by_exact.get(str(t).upper()) or by_norm.get(_norm_ticker(t))
        if cik:
            mapped += 1
            rows.append({"ticker": t, "cik": cik, "is_etf": 0, "mapped_ok": 1, "checked_at": _now_iso()})
        else:
            norm = _norm_ticker(t)
            if norm in ambiguous:
                collisions.append((t, ambiguous[norm]))
            unmapped.append(t)
            rows.append({"ticker": t, "cik": None, "is_etf": 0, "mapped_ok": 0, "checked_at": _now_iso()})

    storage.upsert_cik_map_rows(rows, db_path=db_path)
    print(f"[edgar] CIK map: {mapped} mapped, {etfs} ETFs excluded, {len(unmapped)} UNMAPPED")
    if unmapped:
        print(f"[edgar] UNMAPPED tickers (no company fundamentals will be available): {sorted(unmapped)}")
    for ticker, owners in collisions:
        print(f"[edgar] AMBIGUOUS ticker {ticker}: normalizes the same as {sorted(owners)} — "
              f"REFUSED rather than guessed (a wrong CIK scores one company on another's books)")
    return {"mapped": mapped, "etfs": etfs, "unmapped": unmapped,
            "ambiguous": [t for t, _ in collisions]}


# ---------------------------------------------------------------------------
# Phase 1b/1c — per-company facts fetch + parse into the wide `edgar_facts` store
# ---------------------------------------------------------------------------

def _parse_company_facts(cik, ticker, facts_json):
    """Flatten a companyfacts JSON blob into edgar_facts rows — EVERY us-gaap/dei fact/unit/period, not
    just what value/quality needs (the wide pipe). Structure:
    facts_json['facts'][taxonomy][tag]['units'][unit] -> [ {start,end,val,accn,fy,fp,form,filed}, ... ]."""
    ingested_at = _now_iso()
    facts = (facts_json or {}).get("facts", {}) or {}
    for taxonomy in ("us-gaap", "dei"):
        for tag, tagdata in (facts.get(taxonomy, {}) or {}).items():
            for unit, entries in (tagdata.get("units", {}) or {}).items():
                for e in entries or []:
                    accn, filed, end = e.get("accn"), e.get("filed"), e.get("end")
                    if not (accn and filed and end):
                        continue  # a fact with no accession/filed/period can't be point-in-time gated
                    yield {
                        "cik": cik, "ticker": ticker, "taxonomy": taxonomy, "tag": tag, "unit": unit,
                        # '' (not NULL) for instant/balance-sheet facts, so period_start is a clean key
                        # part; duration facts keep their real start to distinguish 3-month vs YTD.
                        "period_start": e.get("start") or "", "period_end": end,
                        "fiscal_year": e.get("fy"), "fiscal_period": e.get("fp"),
                        "value": _num(e.get("val")), "form": e.get("form"),
                        "accession": accn, "filed_date": filed, "ingested_at": ingested_at,
                    }


def ingest_facts(tickers, db_path=storage.DEFAULT_DB_PATH, limit=None, force=False):
    """Fetch + store EDGAR facts for the mapped, non-ETF subset of `tickers`. Per-CIK (owner-chosen),
    throttled and fail-soft; a company refetched at most every EDGAR['refresh_days'] unless force=True.
    `limit` caps how many companies to ingest (Phase-1 verification on ~10 names). Returns a summary."""
    storage.init_db(db_path)
    cik_map = storage.load_cik_map(db_path=db_path)
    todo = [t for t in tickers if cik_map.get(t, {}).get("mapped_ok") and not cik_map[t].get("is_etf")]
    if limit is not None:
        todo = todo[:limit]

    ingested, skipped_fresh, failed, total_rows = 0, 0, [], 0
    for t in todo:
        cik = cik_map[t]["cik"]
        marker_key = f"edgar_ingest:{cik}"
        if not force:
            last = storage.get_meta(marker_key, db_path=db_path)
            if last:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days
                if age_days < EDGAR["refresh_days"]:
                    skipped_fresh += 1
                    continue
        url = EDGAR["companyfacts_url"].format(cik10=cik)
        blob = _http_get_json(url)
        if blob is None:
            failed.append(t)
            continue
        rows = list(_parse_company_facts(cik, t, blob))
        storage.upsert_edgar_facts(rows, db_path=db_path)
        storage.set_meta(marker_key, _now_iso(), db_path=db_path)
        ingested += 1
        total_rows += len(rows)
        print(f"[edgar] ingested {t} (CIK {cik}): {len(rows)} facts")

    print(f"[edgar] ingest done — companies: {ingested} ingested, {skipped_fresh} fresh-skipped, "
          f"{len(failed)} failed; {total_rows} fact rows written")
    if failed:
        print(f"[edgar] failed companies (skipped, no data invented): {failed}")
    return {"ingested": ingested, "skipped_fresh": skipped_fresh, "failed": failed, "rows": total_rows}


# ---------------------------------------------------------------------------
# Phase 2 — point-in-time resolver: raw facts -> the FUNDAMENTAL_FIELDS ratio dict
# ---------------------------------------------------------------------------

# Balance-sheet concepts are INSTANT (a point-in-time balance, no duration); income/cash-flow concepts
# are FLOWS that must be assembled into a trailing-twelve-month figure.
_INSTANT_CONCEPTS = {"equity", "shares", "assets", "liabilities", "current_assets", "current_liabilities",
                     # debt and lease legs are balance-sheet balances, not flows - they carry no
                     # duration. A concept missing from this set is routed through TTM assembly,
                     # which requires a period_start, so an instant fact silently resolves to None.
                     "debt_long_term", "debt_current",
                     "debt_finance_lease_noncurrent", "debt_finance_lease_current",
                     "debt_finance_lease_total",
                     "debt_operating_lease_noncurrent", "debt_operating_lease_current",
                     "debt_operating_lease_total"}


def _days(a, b):
    """Calendar days from ISO date a to b (b - a)."""
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _split_tag(tag_spec):
    """'dei:EntityCommonStockSharesOutstanding' -> ('dei', 'EntityCommon...'); bare tag -> us-gaap."""
    if ":" in tag_spec:
        tax, name = tag_spec.split(":", 1)
        return tax, name
    return "us-gaap", tag_spec


def _earliest_filed_by_period(facts):
    """Collapse facts to ONE per fiscal period (period_start, period_end), keeping the earliest-filed —
    invariant #2: the originally-filed value wins over a later restatement. Assumes facts already gated
    to filed_date <= D."""
    best = {}
    for f in facts:
        key = (f["period_start"], f["period_end"])
        cur = best.get(key)
        if cur is None or f["filed_date"] < cur["filed_date"]:
            best[key] = f
    return best


def _resolve_instant(facts):
    """Most recent balance for an instant concept: latest period_end, originally-filed. -> (value, prov)."""
    instant = [f for f in facts if not f["period_start"]]
    by_period = _earliest_filed_by_period(instant or facts)
    if not by_period:
        return None, None
    latest = max(by_period.values(), key=lambda f: f["period_end"])
    return latest["value"], latest


def _match_prior_annual(annual, cur, fy):
    """The prior fiscal year's ANNUAL figure that the TTM roll-forward adds to.

    Matching on the `fy` label alone is not enough: EDGAR stamps a filing's fy/fp onto every fact in
    it, INCLUDING prior-period comparatives, so several facts can carry the same label. The structural
    check is that the prior annual must END exactly where the current fiscal year BEGINS
    (FY2023 ends 2023-06-30; the FY2024 YTD that follows starts 2023-07-01). Anything else would be
    adding a year that doesn't abut the stub we're rolling forward."""
    tol = PARAMS["edgar_ttm_span_tolerance_days"]
    if not cur.get("period_start"):
        return None
    for f in annual.values():
        if f.get("fiscal_year") != fy - 1:
            continue
        # gap from prior-annual end to current-period start should be ~1 day
        if abs(_days(f["period_end"], cur["period_start"])) <= tol:
            return f
    return None


def _match_prior_ytd(ytd, quarter, cur, fy, fp):
    """The prior YEAR's same-length year-to-date figure that the TTM roll-forward subtracts.

    THE GUARD THAT MATTERS: the two YTD legs must cover the SAME NUMBER OF DAYS. Matching only on
    (fiscal_year-1, fiscal_period) — as this did originally — can pair a 3-month current stub against
    a 9-month prior-year YTD, yielding `annual + 3mo - 9mo`: a half-year undercount presented with
    full confidence as a TTM. A leg that fails either check means the roll-forward is not safely
    assemblable, so the concept goes MISSING rather than wrong (invariant #2)."""
    tol = PARAMS["edgar_ttm_span_tolerance_days"]
    if not cur.get("period_start"):
        return None
    cur_span = _days(cur["period_start"], cur["period_end"])
    for f in list(ytd.values()) + list(quarter.values()):
        if f.get("fiscal_year") != fy - 1 or f.get("fiscal_period") != fp:
            continue
        if not f.get("period_start"):
            continue
        if abs(_days(f["period_start"], f["period_end"]) - cur_span) > tol:
            continue                                   # duration mismatch -> not comparable
        if abs(_days(f["period_end"], cur["period_end"]) - 365) > tol:
            continue                                   # not actually a year apart
        return f
    return None


def _resolve_ttm(facts):
    """Trailing-twelve-month for a flow concept, correct for US filers (who file only THREE 3-month
    10-Qs a year — Q4 is never a standalone fact). Method, in order:
      1. If the freshest data point is a full annual (10-K) -> use it directly.
      2. Else the freshest point is a fiscal-YTD (10-Q cumulative): TTM = prior-FY annual + current YTD
         - prior-year YTD of the same fiscal period. (The standard roll-forward.)
      3. Fallbacks: sum four clean 3-month quarters spanning ~a year; else the most recent annual (stale
         but valid). Never annualize a single quarter — an incomplete year returns missing.
    Respects non-calendar fiscal years via actual period ends + EDGAR fy/fp. -> (value, prov, method)."""
    resolved = _earliest_filed_by_period(facts)   # one per (start,end), originally-filed
    annual, ytd, quarter = {}, {}, {}             # period_end -> fact
    for (s, e), f in resolved.items():
        if not s:
            continue                              # a flow needs a duration; skip stray instants
        span = _days(s, e)
        if 350 <= span <= 380:
            annual[e] = f
        elif 80 <= span <= 100:
            quarter[e] = f
        elif 100 < span < 350:                    # 6-month / 9-month cumulative YTD
            ytd[e] = f
    all_ends = set(annual) | set(ytd) | set(quarter)
    if not all_ends:
        return None, None, None
    latest_end = max(all_ends)

    # 1) Freshest point is a full year.
    if latest_end in annual:
        f = annual[latest_end]
        return f["value"], f, "annual"

    # 2) Freshest point is a YTD (or lone quarter): annual + current-YTD - prior-year-YTD.
    cur = ytd.get(latest_end) or quarter.get(latest_end)
    if cur is not None and cur.get("fiscal_year") is not None:
        fy, fp = cur["fiscal_year"], cur["fiscal_period"]
        prior_annual = _match_prior_annual(annual, cur, fy)
        prior_ytd = _match_prior_ytd(ytd, quarter, cur, fy, fp)
        if prior_annual and prior_ytd and all(x["value"] is not None for x in (cur, prior_annual, prior_ytd)):
            return prior_annual["value"] + cur["value"] - prior_ytd["value"], cur, "ttm_annual_plus_ytd"

    # 3a) Four clean trailing quarters spanning ~a year (rare for US filers, common for some foreign ones).
    q_ends = sorted(quarter, reverse=True)
    if len(q_ends) >= 4:
        top4 = q_ends[:4]
        if 350 <= _days(quarter[top4[-1]]["period_start"], top4[0]) <= 380 \
                and all(quarter[e]["value"] is not None for e in top4):
            return sum(quarter[e]["value"] for e in top4), quarter[top4[0]], "ttm_4q"
    # 3b) Most recent annual, stale but valid.
    if annual:
        e = max(annual)
        return annual[e]["value"], annual[e], "annual_fallback"
    return None, None, None


def concept_tags():
    """Every XBRL tag any concept chain can resolve — the only tags the resolver ever reads."""
    return sorted({_split_tag(spec)[1] for chain in EDGAR_CONCEPT_TAGS.values() for spec in chain})


def build_facts_index(tickers, db_path=storage.DEFAULT_DB_PATH, extra_tags=()):
    """Pre-load the resolver's read path into memory, filed_date-sorted, for a whole backfill.

    `get_fundamentals_as_of` normally issues one SQL query per (ticker, date). A full backfill is ~533
    dates x ~500 tickers = ~266,000 queries against a 12.8M-row table, measured at ~26 HOURS. Loading
    each ticker's facts ONCE and slicing them by filed_date in memory turns that into ~500 queries.

    Only the tags a concept chain can actually reach are loaded (24 of them, ~1.2M of 12.8M rows), so
    this stays a few hundred MB rather than tens of GB. Returns {ticker: (facts_sorted_by_filed_date,
    [filed_date, ...])} — the parallel date list is what bisect slices against."""
    # `extra_tags` matters: the index is a TAG-FILTERED load, so a caller that needs a tag outside
    # EDGAR_CONCEPT_TAGS (EPS, for SUE) gets an index that silently contains none of its facts.
    tags = sorted(set(concept_tags()) | set(extra_tags))
    index = {}
    for t in tickers:
        facts = storage.load_edgar_facts(t, tags=tags, db_path=db_path)
        facts.sort(key=lambda f: f["filed_date"])
        index[t] = (facts, [f["filed_date"] for f in facts])
    return index


def _facts_as_of(ticker, as_of_date, facts_index, db_path):
    """The ticker's facts filed on or before as_of_date — THE no-lookahead gate for fundamentals.

    Two routes to the same guarantee: SQL (`filed_date <= ?`) when reading the DB directly, or a bisect
    on the pre-sorted filed_date list when a prepared index is supplied. bisect_right returns the count
    of entries <= as_of_date, so the slice is exactly the facts that existed on that date — no fact
    filed later can be in it."""
    if facts_index is None:
        return storage.load_edgar_facts(ticker, filed_on_or_before=as_of_date, db_path=db_path)
    entry = facts_index.get(ticker)
    if not entry:
        return []
    facts, filed_dates = entry
    return facts[:bisect_right(filed_dates, as_of_date)]


def get_fundamentals_as_of(ticker, as_of_date, price=None, sector=None, db_path=storage.DEFAULT_DB_PATH,
                           facts_index=None):
    """Resolve EDGAR raw facts into the SAME FUNDAMENTAL_FIELDS ratio dict yfinance produced, strictly
    point-in-time as of `as_of_date` (only facts with filed_date <= as_of_date), originally-filed (not
    restated). Price-based ratios need `price` (the as-of close) × EDGAR shares; quality ratios are pure.
    Returns the ratio dict plus a `_provenance` map (which tag resolved each concept, its filed_date,
    period_end, and data-age in days) — provenance is how we debug a wrong number later.

    A concept that can't be resolved is None (missing) → its component sits out downstream. Financials/
    REITs get their COGS/operating-margin concept sat out (not comparable), per the spec."""
    facts = _facts_as_of(ticker, as_of_date, facts_index, db_path)
    by_tag = {}
    for f in facts:
        by_tag.setdefault((f["taxonomy"], f["tag"]), []).append(f)

    prov = {}
    max_age = PARAMS["edgar_max_data_age_days"]

    def resolve(concept):
        """Resolve ONE concept through its tag fallback chain, FRESHEST CANDIDATE WINS.

        Why not "first tag that yields a value" (the original rule): filers abandon tags. NVDA stopped
        tagging RevenueFromContractWithCustomerExcludingAssessedTax after FY2022 and moved to Revenues,
        but the dead tag still holds a complete FY2022 annual — so first-match returned a 4.4-year-old
        revenue with `method="annual"` and full confidence, while operating income resolved correctly to
        the current TTM. The resulting operating_margin was 603%. 40 of 360 filers share that pattern.

        So: evaluate EVERY tag in the chain, keep the candidate with the newest period_end (ties broken
        by chain order, i.e. the more-preferred tag), then refuse it outright if it is older than
        `edgar_max_data_age_days`. A filer that has genuinely stopped reporting SITS OUT — a missing
        concept is honest, an ancient one masquerading as current is not (invariant #2)."""
        candidates = []
        for order, tag_spec in enumerate(EDGAR_CONCEPT_TAGS.get(concept, [])):
            tf = by_tag.get(_split_tag(tag_spec))
            if not tf:
                continue
            if concept in _INSTANT_CONCEPTS:
                val, p = _resolve_instant(tf)
                method = "instant"
            else:
                val, p, method = _resolve_ttm(tf)
            if val is not None:
                candidates.append((p["period_end"], -order, val, p, method, tag_spec))

        if not candidates:
            prov[concept] = None                      # nothing in the chain assembled at all
            return None

        # freshest period_end wins; -order makes an earlier (more preferred) tag win a tie
        period_end, _neg_order, val, p, method, tag_spec = max(candidates)
        data_age = _days(period_end, as_of_date)
        if data_age > max_age:
            # every candidate is at least this stale (this one is the freshest), so the concept sits out
            prov[concept] = {"tag": tag_spec, "missing_reason": "stale", "period_end": period_end,
                             "data_age_days": data_age, "max_age_days": max_age,
                             "n_candidates": len(candidates), "n_stale_rejected": len(candidates)}
            return None

        prov[concept] = {"tag": tag_spec, "method": method, "filed_date": p["filed_date"],
                         "period_end": period_end, "age_days": _days(p["filed_date"], as_of_date),
                         "data_age_days": data_age, "n_candidates": len(candidates)}
        return val

    def resolve_debt():
        """Total INTEREST-BEARING debt = long-term leg + current leg.

        Not total Liabilities (which sweeps in payables, deferred revenue, pension obligations — a
        different and much larger number), and not one tag: filers split debt across a long-term and a
        current leg, each with its own chain. The long-term leg is REQUIRED; the current leg is added
        only when present. A missing current leg is NOT imputed as zero — absence of a tag is not
        evidence of no short-term debt — so the total is flagged `debt_partial` and stays auditable."""
        long_term = resolve(EDGAR_DEBT_LEGS["required"])
        current = resolve(EDGAR_DEBT_LEGS["optional"])
        if long_term is None:
            prov["debt_total"] = None
            return None
        total = long_term + (current or 0.0)

        # LEASE OBLIGATIONS. Under ASC 842 both finance and operating leases are balance-sheet
        # liabilities, and yfinance's totalDebt includes them. Leaving them out understated
        # debt_to_equity by a systematic ~6-9% that grew as companies got smaller, because small caps
        # lease proportionally more of what they operate.
        #
        # The double-count guard matters: some filers report LongTermDebtAndCapitalLeaseObligations,
        # which ALREADY bundles finance leases. Adding a finance-lease leg on top of that tag would
        # count the same obligation twice, so that leg is skipped when debt resolved through it.
        lt_tag = (prov.get(EDGAR_DEBT_LEGS["required"]) or {}).get("tag")
        lt_bundles_leases = lt_tag in EDGAR_DEBT_TAGS_INCLUDING_LEASES
        leases = {}
        for i, (parts, combined) in enumerate(EDGAR_LEASE_LEGS):
            is_finance = i == 0
            if is_finance and lt_bundles_leases:
                leases["finance_lease"] = "skipped_already_in_debt_tag"
                continue
            vals = [resolve(p) for p in parts]
            present = [v for v in vals if v is not None]
            # sum the noncurrent+current split when either is present; else the single combined tag
            amount = sum(present) if present else resolve(combined)
            name = "finance_lease" if is_finance else "operating_lease"
            leases[name] = amount
            if amount:
                total += amount

        prov["debt_total"] = {"long_term": long_term, "current": current,
                              "debt_partial": current is None, "leases": leases,
                              "long_term_tag_bundles_leases": lt_bundles_leases, "value": total}
        return total

    revenue = resolve("revenue")
    net_income = resolve("net_income")
    equity = resolve("equity")
    shares = resolve("shares")
    resolve("assets")  # resolved into provenance now; consumed by future factors (asset growth, GP/A)
    liabilities = resolve("liabilities")
    current_assets = resolve("current_assets")
    current_liabilities = resolve("current_liabilities")
    op_income = resolve("operating_income")
    total_debt = resolve_debt()

    is_financial = sector in EDGAR_FINANCIAL_SECTORS

    # NEGATIVE SHAREHOLDERS' EQUITY breaks every equity-denominated ratio, and not harmlessly.
    # Clorox and DaVita carry negative book equity (large buybacks), so debt/equity computes to
    # roughly -3,700. `debt_to_equity` is an INVERTED quality field (lower = better), which would rank
    # the most-levered company in the index as the LOWEST-leverage, highest-quality name in it. ROE is
    # equally meaningless: a negative denominator flips the sign of a perfectly healthy profit.
    # These ratios are undefined here, so they SIT OUT — that is what missing data is for (invariant #2).
    equity_usable = equity is not None and equity > 0

    def ratio(num, den, scale=1.0):
        return (num / den * scale) if (num is not None and den not in (None, 0)) else None

    def aligned(concept_a, concept_b):
        """True when two FLOW concepts describe the same twelve months.

        A margin divides one flow by another, so both legs must cover the same window. Filers routinely
        make one leg resolvable a quarter ahead of the other (an annual revenue to Dec-31 alongside a TTM
        operating income to Mar-31), and dividing across that gap produces a number that looks entirely
        reasonable and means nothing. Misaligned -> the margin sits out (invariant #2)."""
        pa, pb = prov.get(concept_a), prov.get(concept_b)
        if not pa or not pb or "method" not in pa or "method" not in pb:
            return False
        return abs(_days(pa["period_end"], pb["period_end"])) <= PARAMS["edgar_ratio_period_tolerance_days"]

    margins_aligned = aligned("net_income", "revenue")
    op_margin_aligned = aligned("operating_income", "revenue")

    market_cap = (price * shares) if (price is not None and shares) else None

    out = {
        # value (price-based)
        "trailing_pe": ratio(market_cap, net_income),
        "forward_pe": None,                 # not derivable from historical filings
        "price_to_sales": ratio(market_cap, revenue),
        "price_to_book": ratio(market_cap, equity),
        "ev_to_ebitda": None,               # needs debt/cash/ebitda tags — wide-pipe future addition
        # quality (pure fundamentals)
        "profit_margin": ratio(net_income, revenue) if margins_aligned else None,
        "operating_margin": (None if (is_financial or not op_margin_aligned)
                             else ratio(op_income, revenue)),
        "return_on_equity": ratio(net_income, equity) if equity_usable else None,
        # interest-bearing debt / equity, expressed as a PERCENT to match yfinance's convention
        # exactly — so v0.3 (yfinance) and v0.4 (EDGAR) snapshots stay directly comparable.
        "debt_to_equity": (ratio(total_debt, equity, EDGAR_DEBT_TO_EQUITY_SCALE)
                           if equity_usable else None),
        "current_ratio": ratio(current_assets, current_liabilities),
        # context-only / not-from-EDGAR
        "earnings_growth": None, "revenue_growth": None,          # YoY — future factor
        "short_percent_of_float": None, "short_ratio": None,      # short interest stays live-only (FINRA)
        "_provenance": prov,
    }
    # Gate-withheld fields sit out rather than entering a score unverified (see EDGAR_EXCLUDED_FIELDS).
    # Computed above and then dropped deliberately, so re-enabling one is a config edit and a re-derive
    # — never a re-ingest. The provenance for the underlying concepts is left intact for diagnosis.
    for field in EDGAR_EXCLUDED_FIELDS:
        out[field] = None
    return out


# ---------------------------------------------------------------------------
# Phase 3 — validation gate: does the EDGAR pipe reproduce yfinance TODAY?
# ---------------------------------------------------------------------------

def build_validation_report(tickers, price_by_ticker, sector_by_ticker,
                            db_path=storage.DEFAULT_DB_PATH, output_dir=None):
    """Compare CURRENT fundamentals derived from EDGAR against the stored yfinance `fundamentals` cache,
    per ticker+concept, and write output/edgar_validation_report.csv (worst % differences first). Prints a
    per-concept summary (correlation, median abs % diff, count differing >20%). This is the GATE: review
    it before any historical backfill — a wrong tag mapping backfilled across years is a confident lie.

    Returns the summary DataFrame. Small diffs are expected (yfinance uses its own TTM/estimate
    conventions); large or structural divergence for a concept means its tag mapping needs work."""
    output_dir = output_dir or os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()

    rows = []
    for t in tickers:
        if not storage.get_cik(t, db_path=db_path):
            continue  # ETF / unmapped — no EDGAR fundamentals to compare
        yf = storage.get_cached_fundamentals(t, db_path=db_path)
        if not yf:
            continue  # no yfinance baseline to compare against
        # PRICE ALIGNMENT — otherwise the gate measures its own noise. trailing_pe / price_to_sales /
        # price_to_book are all market_cap-based, and the cached yfinance row computed its ratio using
        # the price on the day IT was fetched. The fundamentals cache refreshes on a rolling ~1/5 per
        # night, so a row can be several days and several percent of price movement old. Pricing the
        # EDGAR side at today's close compares two different days and injects a diff the same size as
        # the one being measured (it moved trailing_pe from Spearman 0.903 to 0.859 across two runs
        # 20 minutes apart, with no code change in between). Price both sides on the SAME day so the
        # comparison isolates the fundamentals, which is the only thing the gate is meant to test.
        as_of, price = _yf_row_price_basis(t, yf, price_by_ticker, today, db_path)
        ed = get_fundamentals_as_of(t, as_of, price=price,
                                    sector=sector_by_ticker.get(t), db_path=db_path)
        for c in _VALIDATION_CONCEPTS:
            ev, yv = ed.get(c), yf.get(c)
            pct = (abs(ev - yv) / abs(yv) * 100.0) if (ev is not None and yv not in (None, 0)) else None
            rows.append({"ticker": t, "concept": c, "edgar": ev, "yfinance": yv,
                         "abs_pct_diff": pct,
                         "edgar_missing": ev is None, "yf_missing": yv is None})

    detail = pd.DataFrame(rows)
    report_path = os.path.join(output_dir, "edgar_validation_report.csv")
    detail.sort_values("abs_pct_diff", ascending=False, na_position="last").to_csv(report_path, index=False)

    # Per-concept summary.
    summary_rows = []
    for c in _VALIDATION_CONCEPTS:
        sub = detail[detail["concept"] == c]
        both = sub[sub["edgar"].notna() & sub["yfinance"].notna()]
        # Spearman (rank) — NOT Pearson. These are fat-tailed ratios: one company with near-zero equity
        # sends P/E or ROE to five figures and single-handedly sets a Pearson correlation, which is why
        # the first gate showed trailing_pe corr=-0.015 while its median abs diff was a healthy 3.1%.
        # Rank correlation answers the question that actually matters: does EDGAR order the universe the
        # same way yfinance does? Pearson is kept alongside it, labelled, for reference only.
        pearson = both["edgar"].corr(both["yfinance"]) if len(both) >= 3 else None
        spearman = (both["edgar"].rank().corr(both["yfinance"].rank())
                    if len(both) >= 3 else None)
        median_pct = both["abs_pct_diff"].median() if len(both) else None
        share_gt_100 = float((both["abs_pct_diff"] > 100).mean()) if len(both) else None
        summary_rows.append({
            "concept": c,
            "n_both_present": len(both),
            "edgar_missing": int(sub["edgar_missing"].sum()),
            "spearman": round(spearman, 3) if spearman is not None and pd.notna(spearman) else None,
            "pearson_ref_only": round(pearson, 3) if pearson is not None and pd.notna(pearson) else None,
            "median_abs_pct_diff": round(median_pct, 1) if median_pct is not None and pd.notna(median_pct) else None,
            "share_diff_gt_100pct": round(share_gt_100, 3) if share_gt_100 is not None else None,
            "count_diff_gt_20pct": int((both["abs_pct_diff"] > 20).sum()),
        })
    summary = pd.DataFrame(summary_rows)
    summary["passes_gate"] = summary.apply(_concept_passes_gate, axis=1)
    # An ACCEPTED-DESPITE-FAILING concept must say so in the artifact itself, with its reason, so the
    # record shows why a criterion was judged inapplicable rather than merely missed. Silence here is
    # how "close enough" becomes precedent.
    summary["disposition"] = [
        _GATE_DISPOSITIONS.get(c, {}).get("disposition",
                                          "pass" if p else "FAIL — blocks backfill")
        for c, p in zip(summary["concept"], summary["passes_gate"])]
    summary["disposition_reason"] = [_GATE_DISPOSITIONS.get(c, {}).get("reason", "")
                                     for c in summary["concept"]]

    print(f"[edgar] validation report ({len(detail)} ticker-concept rows) -> {report_path}")
    print(summary.to_string(index=False))
    # A deliberately withheld field is not a gate failure — it never enters a score, so it has nothing
    # to prove. Counting it as one would train the reader to ignore a red banner that is always on.
    failed = summary[~summary["passes_gate"] & ~summary["concept"].isin(EDGAR_EXCLUDED_FIELDS)
                     ]["concept"].tolist()
    withheld = sorted(set(summary["concept"]) & set(EDGAR_EXCLUDED_FIELDS))
    if withheld:
        print(f"[edgar] withheld from scoring (not evaluated): {', '.join(withheld)}")
    if failed:
        print(f"[edgar] GATE FAILED for {len(failed)} concept(s): {', '.join(failed)} — "
              f"do NOT backfill until these are fixed")
    else:
        print(f"[edgar] GATE PASSED — all {len(summary) - len(withheld)} scored concepts clear the "
              f"pre-registered bar "
              f"(median abs diff < {PARAMS['edgar_gate_max_median_pct_diff']}%, "
              f"Spearman > {PARAMS['edgar_gate_min_spearman']}, "
              f">100% diffs < {PARAMS['edgar_gate_max_share_gt_100pct']:.0%})")
    return summary


def _yf_row_price_basis(ticker, yf_row, price_by_ticker, today, db_path):
    """(as_of_date, price) to evaluate the EDGAR side on, matched to when the yfinance row was fetched.

    Returns the last close at or before the cache row's fetch date, so both sides of a market-cap ratio
    use the same day's price. Falls back to today's close when the fetch timestamp or that day's bar is
    unavailable — never invents a price (invariant #2)."""
    fetched = (yf_row.get("timestamp_fetched") or "")[:10]
    if not fetched:
        return today, price_by_ticker.get(ticker)
    history = storage.load_price_history(ticker, db_path=db_path)
    prior = [r for r in history if r["date"] <= fetched]
    if not prior:
        return today, price_by_ticker.get(ticker)
    return fetched, prior[-1]["close"]


# Owner dispositions for concepts whose gate result required a judgement call (2026-08-09 review).
# Recorded HERE, next to the gate, so the reasoning ships with the report rather than living only in a
# chat log. A concept absent from this map is governed purely by the numeric bar.
_GATE_DISPOSITIONS = {
    "return_on_equity": {
        "disposition": "pass (was marginal against a STALE ingest — no judgement call needed)",
        "reason": ("Recorded because the first reading nearly became one. Against an EDGAR store last "
                   "ingested 2026-07-28 — while the yfinance cache had refreshed through 08-17 and so "
                   "already held Q2 10-Q figures — ROE missed the >100%-tail criterion (5.5% vs 5.0%) "
                   "and an argument was built that the criterion was measuring near-zero-denominator "
                   "instability rather than mapping disagreement. That argument was TRUE but it was "
                   "also unnecessary: re-ingesting and re-running put ROE at Spearman 0.978 / median "
                   "5.6% / tail 3.7%, clearing all three criteria outright. LESSON: when a result sits "
                   "near the bar, re-measure on fresh inputs BEFORE reasoning about why the bar might "
                   "not apply. The instinct to explain a marginal miss is the failure mode the "
                   "pre-registered bar exists to catch."),
    },
    "operating_margin": {
        "disposition": "EXCLUDED from v0.4 (EDGAR_EXCLUDED_FIELDS)",
        "reason": ("Failed all three criteria. Systematic ~9% one-directional gap across 75% of names "
                   "that survived every fix including period alignment => definitional, not a bug. "
                   "Hypothesis: yfinance publishes NORMALIZED operating income vs us-gaap as-reported "
                   "OperatingIncomeLoss (consistent with yf showing negative margins for PANW/COO). "
                   "Plausible but UNVERIFIED, so it sits out rather than entering a score. See ROADMAP."),
    },
}


def _concept_passes_gate(row):
    """The PRE-REGISTERED pass bar from config, applied per concept. Written down before the numbers
    were seen so a marginal result can't be talked into a pass — every criterion must clear."""
    if not row["n_both_present"]:
        return False
    checks = [
        row["median_abs_pct_diff"] is not None
        and row["median_abs_pct_diff"] < PARAMS["edgar_gate_max_median_pct_diff"],
        row["spearman"] is not None and row["spearman"] > PARAMS["edgar_gate_min_spearman"],
        row["share_diff_gt_100pct"] is not None
        and row["share_diff_gt_100pct"] < PARAMS["edgar_gate_max_share_gt_100pct"],
    ]
    return bool(all(checks))


# ---------------------------------------------------------------------------
# Quarterly EPS series — the input to SUE (standardized unexpected earnings)
# ---------------------------------------------------------------------------

EPS_TAGS = ["EarningsPerShareDiluted", "EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"]


def quarterly_eps(ticker, db_path=storage.DEFAULT_DB_PATH, facts_index=None):
    """A ticker's 3-MONTH EPS history as [(period_end, filed_date, eps), ...], oldest first.

    Two disciplines carried over from the ratio resolver, for the same reasons:
      * ORIGINALLY-FILED WINS. One value per fiscal period, keeping the earliest filing. A later
        restatement did not exist when the market reacted, and an earnings surprise measured against
        restated history is a surprise nobody could have traded.
      * FILED DATE IS THE USABLE DATE, not period_end. A quarter ending 2025-03-31 is typically not
        public until early May; treating the period end as the knowledge date is a ~5-week lookahead
        and would manufacture exactly the post-announcement drift this is meant to measure.

    Only clean 3-month periods are kept — YTD and annual spans are excluded rather than differenced,
    because differencing across a restated or re-segmented year silently fabricates a quarter."""
    if facts_index is not None:
        facts = facts_index.get(ticker, ([], []))[0]
    else:
        facts = storage.load_edgar_facts(ticker, tags=EPS_TAGS, db_path=db_path)

    by_tag = {}
    for f in facts:
        if f["tag"] in EPS_TAGS:
            by_tag.setdefault(f["tag"], []).append(f)

    for tag in EPS_TAGS:                      # preference order, first tag with a usable series wins
        tf = by_tag.get(tag)
        if not tf:
            continue
        best = {}
        for f in tf:
            s, e = f.get("period_start"), f.get("period_end")
            if not s or not e or f.get("value") is None:
                continue
            if not (80 <= _days(s, e) <= 100):        # 3-month periods only
                continue
            cur = best.get((s, e))
            if cur is None or f["filed_date"] < cur["filed_date"]:
                best[(s, e)] = f                      # earliest-filed wins
        series = sorted(((f["period_end"], f["filed_date"], float(f["value"]))
                         for f in best.values()), key=lambda r: r[0])
        if len(series) >= 5:                          # need a year of history plus the current quarter
            return series
    return []
