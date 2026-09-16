"""Fetching layer: yfinance OHLCV + earnings dates, with rate-limit hardening.

Rules (see CLAUDE.md):
- Never invent data. A failed ticker is logged and skipped, never crashes the run.
- Cache to SQLite; only fetch the incremental missing tail on subsequent runs.
- Batch + retry-with-backoff to stay under Yahoo's ~360 req/hr unofficial limit.
"""

import math
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from src import storage
from src.config import FUNDAMENTAL_FIELDS, FUNDAMENTAL_INFO_KEYS, PARAMS

try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:  # older yfinance versions may not expose this
    YFRateLimitError = Exception


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _download_with_retry(tickers, start=None, end=None, period=None):
    """Wraps yf.download with exponential backoff. Returns the raw DataFrame, or None
    if every retry failed (caller logs and skips — never raises out of the batch)."""
    max_retries = PARAMS["yfinance_max_retries"]
    backoff_base = PARAMS["yfinance_backoff_base_sec"]

    kwargs = {"auto_adjust": True, "group_by": "ticker", "progress": False}
    if period is not None:
        kwargs["period"] = period
    else:
        kwargs["start"] = start
        kwargs["end"] = end

    last_error = None
    for attempt in range(max_retries):
        try:
            df = yf.download(tickers, **kwargs)
            return df
        except YFRateLimitError as e:
            last_error = e
            sleep_for = backoff_base * (2 ** attempt)
            print(f"[data] rate-limited fetching {tickers}, retry {attempt + 1}/{max_retries} in {sleep_for:.1f}s")
            time.sleep(sleep_for)
        except Exception as e:
            last_error = e
            sleep_for = backoff_base * (2 ** attempt)
            print(f"[data] error fetching {tickers} ({e}), retry {attempt + 1}/{max_retries} in {sleep_for:.1f}s")
            time.sleep(sleep_for)
    print(f"[data] giving up on {tickers} after {max_retries} retries: {last_error}")
    return None


def _rows_from_download(df, ticker):
    """Extract OHLCV rows for one ticker out of a (possibly multi-ticker) yf.download frame."""
    if df is None or df.empty:
        return []
    try:
        sub = df[ticker] if isinstance(df.columns, pd.MultiIndex) else df
    except KeyError:
        return []
    sub = sub.dropna(subset=["Close"])
    timestamp_fetched = _now_iso()
    rows = []
    for idx, r in sub.iterrows():
        rows.append({
            "ticker": ticker,
            "date": idx.strftime("%Y-%m-%d"),
            "open": float(r["Open"]) if pd.notna(r["Open"]) else None,
            "high": float(r["High"]) if pd.notna(r["High"]) else None,
            "low": float(r["Low"]) if pd.notna(r["Low"]) else None,
            "close": float(r["Close"]) if pd.notna(r["Close"]) else None,
            "volume": float(r["Volume"]) if pd.notna(r["Volume"]) else None,
            "timestamp_fetched": timestamp_fetched,
        })
    return rows


def fetch_price_history(tickers, db_path=storage.DEFAULT_DB_PATH, period=None):
    """Cache-aware fetch for a list of tickers. Tickers with no cache are batched together
    for a full-period download; tickers with existing cache are fetched incrementally
    (one call per ticker, since each has its own missing-tail start date).

    Returns a summary dict: {"fresh": [...], "cached_only": [...], "failed": [...]}.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    period = period or PARAMS["fetch_period"]
    storage.init_db(db_path)

    today = datetime.now(timezone.utc).date()
    needs_full = []
    needs_incremental = {}  # ticker -> start_date
    for t in tickers:
        cached_dates = storage.get_cached_dates(t, db_path=db_path)
        if not cached_dates:
            needs_full.append(t)
        else:
            last_cached = datetime.strptime(cached_dates[-1], "%Y-%m-%d").date()
            if last_cached >= today - timedelta(days=1):
                continue  # already fresh, no fetch needed
            needs_incremental[t] = last_cached + timedelta(days=1)

    fresh, cached_only, failed = [], [], []
    batch_size = PARAMS["yfinance_batch_size"]
    batch_delay = PARAMS["yfinance_batch_delay_sec"]

    # Full-period downloads, batched.
    for i in range(0, len(needs_full), batch_size):
        batch = needs_full[i:i + batch_size]
        df = _download_with_retry(batch, period=period)
        for t in batch:
            rows = _rows_from_download(df, t)
            if rows:
                storage.upsert_price_rows(rows, db_path=db_path)
                fresh.append(t)
            else:
                failed.append(t)
        if i + batch_size < len(needs_full):
            time.sleep(batch_delay)

    # Incremental tail downloads, BATCHED by shared start date. On a normal daily run every cached
    # ticker shares the same missing-tail start (the last trading day), so grouping by start_date
    # collapses ~N per-ticker calls — each previously paying a batch_delay — into ~N/batch_size
    # multi-ticker calls. This is the dominant lever on the daily run's wall-clock (per-ticker delays
    # were ~N × batch_delay), and fewer requests is also gentler on Yahoo's ~360/hr limit. A one-bar
    # tail is tiny, so a multi-ticker download is cheap; _rows_from_download already de-multiplexes a
    # multi-ticker frame (same call the full-period path uses).
    end_str = (today + timedelta(days=1)).isoformat()
    by_start = defaultdict(list)
    for t, start_date in needs_incremental.items():
        by_start[start_date].append(t)
    inc_batches = [(start_date, group[i:i + batch_size])
                   for start_date, group in by_start.items()
                   for i in range(0, len(group), batch_size)]
    for bi, (start_date, batch) in enumerate(inc_batches):
        df = _download_with_retry(batch, start=start_date.isoformat(), end=end_str)
        for t in batch:
            rows = _rows_from_download(df, t)
            if rows:
                storage.upsert_price_rows(rows, db_path=db_path)
                fresh.append(t)
            else:
                # No new rows is expected if there's been no new trading day; not a failure.
                cached_only.append(t)
        if bi + 1 < len(inc_batches):
            time.sleep(batch_delay)

    cached_only.extend(t for t in tickers if t not in fresh and t not in failed and t not in cached_only)

    print(f"[data] fetch summary — fresh: {len(fresh)}, cached-only: {len(cached_only)}, failed: {len(failed)}")
    if failed:
        print(f"[data] failed tickers (skipped, no data invented): {failed}")

    return {"fresh": fresh, "cached_only": cached_only, "failed": failed}


def _coerce_number(value):
    """yfinance .info values are usually float/int but occasionally strings or odd types.
    Return a plain float, or None if it isn't a finite number. Never guesses a value."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _extract_info_fields(info):
    """Pull our FUNDAMENTAL_FIELDS out of a yfinance Ticker.info dict, mapping each via
    FUNDAMENTAL_INFO_KEYS and coercing to float/None. A key absent from .info -> None (never
    invented). Returns (fields_dict, any_present: bool)."""
    fields = {}
    any_present = False
    for field in FUNDAMENTAL_FIELDS:
        raw = info.get(FUNDAMENTAL_INFO_KEYS[field]) if isinstance(info, dict) else None
        val = _coerce_number(raw)
        fields[field] = val
        if val is not None:
            any_present = True
    return fields, any_present


def _is_cache_fresh(cached_row, refresh_days):
    """A cached fundamentals row is reusable without a refetch if its timestamp is within
    refresh_days. Stale or unparseable timestamp -> not fresh (will attempt a refetch)."""
    if cached_row is None:
        return False
    ts = cached_row.get("timestamp_fetched")
    if not ts:
        return False
    try:
        fetched = datetime.fromisoformat(ts)
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched) <= timedelta(days=refresh_days)


def _cache_age_days(cached_row):
    """Age of a cached fundamentals row in days (now - timestamp_fetched). No cache / missing /
    unparseable timestamp -> +inf, so a never-fetched ticker always sorts oldest (top refresh
    priority). Drives the rolling refresh queue — deterministic and auditable off existing state."""
    if cached_row is None:
        return float("inf")
    ts = cached_row.get("timestamp_fetched")
    if not ts:
        return float("inf")
    try:
        fetched = datetime.fromisoformat(ts)
    except ValueError:
        return float("inf")
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 86400.0


def fetch_fundamentals(tickers, db_path=storage.DEFAULT_DB_PATH, refresh_days=None):
    """Cache-aware, throttled, fail-soft fetch of per-ticker fundamental + short-interest
    fields via yfinance Ticker.info (the most rate-limit-prone endpoint, hence the aggressive
    cache and per-ticker delay). LIVE-RUN ONLY — these fields are point-in-time as of fetch and
    are never reconstructed for backfill.

    For each ticker: reuse the cached row if it is within refresh_days; otherwise fetch fresh
    and upsert. On any fetch error the ticker is logged and skipped (existing stale cache, if
    any, is still returned — real-but-old beats invented), never crashing the run.

    Returns dict[ticker -> {field -> value or None}] for every requested ticker.
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    refresh_days = refresh_days if refresh_days is not None else PARAMS["fundamentals_refresh_days"]
    delay = PARAMS["fundamentals_fetch_delay_sec"]
    storage.init_db(db_path)

    # Load each ticker's cached row + age once, then refetch only a rolling ~1/refresh_days SLICE this
    # run — not "everything that's stale", which spikes every refresh_days-th run when the whole universe
    # (fetched together) expires together.
    cache = {t: storage.get_cached_fundamentals(t, db_path=db_path) for t in tickers}
    age = {t: _cache_age_days(cache[t]) for t in tickers}
    n = max(1, math.ceil(len(tickers) / refresh_days)) if tickers else 0
    ranked = sorted(tickers, key=lambda t: (-age[t], t))            # oldest first, ties by ticker
    # Refetch ONLY the n oldest — a hard cap, deliberately NO "also refetch everything over tolerance"
    # guard. A guard would re-synchronize a synchronized cache (refetch the whole batch together -> they
    # all expire together -> a perpetual 5-day spike), defeating the flattening. Capping at n staggers
    # the universe and stays flat forever. The trade: draining an over-tolerance BACKLOG (today's
    # synchronized cache, or after several missed nights) takes ceil(backlog/n) nights, during which the
    # most-stale names drift a few days past refresh_days — a one-time, self-healing, LOGGED transient
    # (fundamentals barely move over those extra days). Never-cached tickers (age +inf) sort oldest, so
    # they fill through this same quota (~n/night), and sit out (flagged fundamentals_missing) until then.
    to_refresh = set(ranked[:n])

    result = {}
    fetched_count, reused_count, failed, refreshed_ok = 0, 0, [], set()
    for t in tickers:
        cached = cache[t]
        if t not in to_refresh:
            result[t] = {f: (cached.get(f) if cached else None) for f in FUNDAMENTAL_FIELDS}
            reused_count += 1
            continue
        try:
            info = yf.Ticker(t).info
            fields, any_present = _extract_info_fields(info)
            storage.upsert_fundamentals(t, fields, _now_iso(), fetch_failed=not any_present, db_path=db_path)
            result[t] = fields
            fetched_count += 1
            refreshed_ok.add(t)
        except Exception as e:
            print(f"[data] fundamentals fetch failed for {t} ({e}) — skipped, no data invented")
            failed.append(t)
            # Keep prior cached values (else all-None). The timestamp is NOT advanced, so this ticker
            # stays oldest and is retried on the very next run — fail-soft, never blocks.
            result[t] = {f: (cached.get(f) if cached else None) for f in FUNDAMENTAL_FIELDS}
        time.sleep(delay)

    # Oldest fundamental age AFTER this run's refresh (refreshed -> ~0), logged so drift is visible and a
    # value creeping past the tolerance is obvious.
    post_age = max(((0.0 if t in refreshed_ok else age[t]) for t in tickers), default=0.0)
    oldest_str = "n/a" if post_age == float("inf") else f"{post_age:.1f}d"
    print(f"[data] fundamentals rolling — fetched: {fetched_count}, reused-cache: {reused_count}, "
          f"failed: {len(failed)}; oldest age now {oldest_str} (tolerance {refresh_days}d)")
    if failed:
        print(f"[data] fundamentals failed tickers (skipped): {failed}")
    return result


def fetch_earnings_dates(tickers, db_path=storage.DEFAULT_DB_PATH, refresh_days=None):
    """Cached, throttled, rolling-slice next-earnings dates for a whole universe.

    Replaces a per-ticker uncached network call made inside the scoring loop. That call issued one raw
    HTTP request per ticker PER RUN with no throttle and no cache — 519 requests a night against
    Yahoo's ~360/hr soft limit, and the most likely single cause of an IP block as the universe grows.
    A block stops data collection entirely, which is the one failure this project cannot absorb.

    Same shape as `fetch_fundamentals`: refetch only the ~1/refresh_days OLDEST slice each run, so a
    universe fetched together does not expire together and re-spike. Everything else is served from
    cache. Returns dict[ticker -> (date_or_None, missing_flag)].
    """
    if isinstance(tickers, str):
        tickers = [tickers]
    refresh_days = refresh_days if refresh_days is not None else PARAMS["earnings_refresh_days"]
    delay = PARAMS["earnings_fetch_delay_sec"]
    storage.init_db(db_path)

    cache = {t: storage.get_cached_earnings_date(t, db_path=db_path) for t in tickers}
    age = {t: _cache_age_days(cache[t]) for t in tickers}
    n = max(1, math.ceil(len(tickers) / refresh_days)) if tickers else 0
    ranked = sorted(tickers, key=lambda t: (-age[t], t))          # oldest first, ties by ticker
    to_refresh = set(ranked[:n])

    def _from_cache(row):
        if not row or not row.get("earnings_date"):
            return None, True
        return row["earnings_date"], False

    result, fetched, reused, failed = {}, 0, 0, []
    for t in tickers:
        if t not in to_refresh:
            result[t] = _from_cache(cache[t])
            reused += 1
            continue
        d, missing = fetch_next_earnings_date(t)
        # Store the ISO date string; a genuine "no date published" is recorded as NULL + fetch_failed,
        # which is different from "never asked" (no row at all) and must stay distinguishable.
        iso = d.isoformat() if hasattr(d, "isoformat") else (str(d) if d is not None else None)
        storage.upsert_earnings_date(t, iso, _now_iso(), fetch_failed=missing, db_path=db_path)
        result[t] = (iso, missing)
        fetched += 1
        if missing:
            failed.append(t)
        time.sleep(delay)

    post_age = max(((0.0 if t in to_refresh else age[t]) for t in tickers), default=0.0)
    oldest = "n/a" if post_age == float("inf") else f"{post_age:.1f}d"
    print(f"[data] earnings rolling — fetched: {fetched}, reused-cache: {reused}, "
          f"no-date: {len(failed)}; oldest age now {oldest} (tolerance {refresh_days}d)")
    return result


def fetch_next_earnings_date(ticker):
    """Best-effort next earnings date via yfinance. Never invents a date.

    Returns (date_or_None, earnings_date_missing: bool).
    """
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        next_date = None
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            dates = cal["Earnings Date"]
            next_date = dates[0] if isinstance(dates, (list, tuple)) and dates else None
        elif hasattr(cal, "empty") and not cal.empty and "Earnings Date" in getattr(cal, "index", []):
            next_date = cal.loc["Earnings Date"].iloc[0]
        if next_date is None:
            return None, True
        return next_date, False
    except Exception as e:
        print(f"[data] could not fetch earnings date for {ticker}: {e}")
        return None, True


def repair_price_gaps(db_path=storage.DEFAULT_DB_PATH, calendar_ticker=None, dry_run=False,
                      max_span_days=30):
    """Refetch sessions a ticker is MISSING inside its own cached span.

    `fetch_price_history` resumes from `cached_dates[-1]`, so it only ever extends the FRONT of a
    series. A hole behind that frontier is invisible to it forever — no retry, no error, nothing in
    any log. This is the only thing that closes one.

    It is not hypothetical and it is not small. Measured 2026-09-15: **752 of 1,527 tickers** were
    missing at least one interior session, and three dates — 2026-07-21, 07-22 and 07-31 — were
    absent for roughly 690 tickers each. A failed run on those nights left half the universe with
    holes. Any forward window spanning a hole comes up short, trips the `idx + n >= len` guardrail
    in `_forward_return`, and silently drops that name from the horizon's statistics — which is how
    a 120-day cohort that should have held ~1,500 names reported 515.

    Refetches only the span actually needed per ticker, batched like every other fetch here.
    `max_span_days` caps how wide a single repair range may be, so one ticker with an ancient hole
    cannot trigger a multi-year re-download.
    """
    calendar_ticker = calendar_ticker or PARAMS["calendar_ticker"]
    calendar = [r["date"] for r in storage.load_price_history(calendar_ticker, db_path=db_path)]
    if not calendar:
        print("[data] no calendar ticker history — cannot detect gaps")
        return {"tickers": 0, "bars_written": 0, "gaps": {}}

    conn = storage._connect(db_path)
    try:
        rows = conn.execute("SELECT ticker, date FROM price_history").fetchall()
    finally:
        conn.close()
    have = {}
    for t, d in rows:
        have.setdefault(t, set()).add(d)

    plan = {}
    for ticker, dates in have.items():
        lo, hi = min(dates), max(dates)
        missing = [d for d in calendar if lo <= d <= hi and d not in dates]
        if missing:
            plan[ticker] = missing
    print(f"[data] gap repair: {len(plan)} ticker(s) with interior holes, "
          f"{sum(len(v) for v in plan.values())} missing bar(s)")
    if dry_run or not plan:
        return {"tickers": len(plan), "bars_written": 0, "gaps": plan}

    # Group by the (start, end) span needed, so tickers sharing the same outage are fetched together
    # rather than one range per name.
    by_span = {}
    for ticker, missing in plan.items():
        start = (date.fromisoformat(min(missing)) - timedelta(days=4)).isoformat()
        end = (date.fromisoformat(max(missing)) + timedelta(days=4)).isoformat()
        if (date.fromisoformat(end) - date.fromisoformat(start)).days > max_span_days:
            print(f"[data]   {ticker}: gap span too wide ({start}..{end}) — skipped, repair by hand")
            continue
        by_span.setdefault((start, end), []).append(ticker)

    written = 0
    batch_size = PARAMS["yfinance_batch_size"]
    for (start, end), tickers in sorted(by_span.items()):
        wanted = {d for t in tickers for d in plan[t]}
        print(f"[data]   repairing {len(tickers)} ticker(s) over {start}..{end}")
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            frames = _download_batch(batch, start=start, end=end)
            for ticker, df in frames.items():
                rows_out = []
                for d, r in df.iterrows():
                    ds = d.strftime("%Y-%m-%d")
                    if ds not in wanted or ds in have.get(ticker, ()):
                        continue     # only fill HOLES; never overwrite a cached bar
                    rows_out.append({
                        "ticker": ticker, "date": ds,
                        "open": _f(r.get("Open")), "high": _f(r.get("High")),
                        "low": _f(r.get("Low")), "close": _f(r.get("Close")),
                        "volume": _f(r.get("Volume")),
                        "timestamp_fetched": datetime.now(timezone.utc).isoformat(),
                    })
                rows_out = [r for r in rows_out if r["close"] is not None]
                written += storage.upsert_price_rows(rows_out, db_path=db_path)
            time.sleep(PARAMS["yfinance_batch_delay_sec"])
    print(f"[data] gap repair wrote {written} bar(s)")
    return {"tickers": len(plan), "bars_written": written, "gaps": plan}


def _f(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _download_batch(tickers, start, end):
    """{ticker: DataFrame} for a date range. Single-ticker frames come back un-multi-indexed, so
    both shapes are normalised here rather than at every call site."""
    import yfinance as yf
    out = {}
    try:
        df = yf.download(list(tickers), start=start, end=end, auto_adjust=True,
                         progress=False, interval="1d", group_by="ticker", threads=False)
    except Exception as exc:
        print(f"[data]   batch {tickers} failed: {exc}")
        return out
    if df is None or df.empty:
        return out
    if isinstance(df.columns, pd.MultiIndex):
        for t in tickers:
            if t in df.columns.get_level_values(0):
                sub = df[t].dropna(how="all")
                if not sub.empty:
                    out[t] = sub
    elif len(tickers) == 1:
        sub = df.dropna(how="all")
        if not sub.empty:
            out[tickers[0]] = sub
    return out


# ---------------------------------------------------------------------------
# Analyst estimate revisions — ACCUMULATE-FORWARD
# ---------------------------------------------------------------------------

# Upward revisions to consensus EPS estimates are the strongest documented anomaly this project has
# never tested, and the one input here that CANNOT BE BOUGHT BACK. Price history and SEC filings can
# be fetched for any past date whenever we get round to them; Yahoo publishes only where estimates
# stand TODAY. So the sample for this factor begins on the first night this function runs, and every
# night it does not run is a night permanently absent from that sample.
#
# NOT SCORED. Collected only. Feeding a live-only input into the score is exactly the mistake v0.6
# was written to undo (see LIVE_PIT_MODEL_VERSION): it would put a factor in the model that no
# backfilled row could ever carry, and re-split one model_version into two different models. It earns
# a place in the score by being MEASURED first — which needs history this table does not have yet.

def _estimate_rows_for_ticker(ticker, trend, revisions, fetched_date, now_iso):
    """Flatten yfinance's two estimate frames into one row per period.

    They are separate frames indexed by the same period labels ('0q', '+1q', '0y', '+1y'), and either
    can be absent or short. Periods are UNIONED rather than intersected so a ticker with a trend but
    no revision counts still records its trend — a partial observation is real data, and dropping it
    would silently shrink the sample."""
    def _cell(frame, period, col):
        try:
            if frame is None or getattr(frame, "empty", True) or period not in frame.index:
                return None
            if col not in frame.columns:
                return None
            v = frame.loc[period, col]
        except Exception:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if pd.isna(f) else f

    def _periods(frame):
        if frame is None or getattr(frame, "empty", True):
            return []
        return [str(p) for p in frame.index]

    def _currency(period):
        for frame in (trend, revisions):
            try:
                if (frame is not None and not getattr(frame, "empty", True)
                        and period in frame.index and "currency" in frame.columns):
                    c = frame.loc[period, "currency"]
                    if isinstance(c, str) and c:
                        return c
            except Exception:
                pass
        return None

    rows = []
    for period in sorted(set(_periods(trend)) | set(_periods(revisions))):
        # Yahoo spells one of these with a capital D ('downLast7Days') and the rest lowercase.
        # Both spellings are tried rather than assumed: a silent None here would read as "no analyst
        # revised down", which is a fabricated signal, not a missing one.
        down7 = _cell(revisions, period, "downLast7Days")
        if down7 is None:
            down7 = _cell(revisions, period, "downLast7days")
        rows.append({
            "ticker": ticker, "fetched_date": fetched_date, "period": period,
            "eps_current": _cell(trend, period, "current"),
            "eps_7d_ago": _cell(trend, period, "7daysAgo"),
            "eps_30d_ago": _cell(trend, period, "30daysAgo"),
            "eps_60d_ago": _cell(trend, period, "60daysAgo"),
            "eps_90d_ago": _cell(trend, period, "90daysAgo"),
            "up_last_7d": _cell(revisions, period, "upLast7days"),
            "up_last_30d": _cell(revisions, period, "upLast30days"),
            "down_last_7d": down7,
            "down_last_30d": _cell(revisions, period, "downLast30days"),
            "currency": _currency(period),
            "fetch_failed": 0, "timestamp_fetched": now_iso,
        })
    return rows


def fetch_estimate_revisions(tickers, db_path=storage.DEFAULT_DB_PATH, refresh_days=None,
                             as_of_date=None):
    """Record today's analyst EPS estimates + revision counts for a rolling slice of the universe.

    Rolling, not exhaustive, for the same reason `fetch_fundamentals` is: ~1,500 requests a night
    against Yahoo's ~360/hour soft limit is the surest way to get the IP blocked, and a block stops
    ALL data collection, including the irreplaceable kind. The slice costs ~1/refresh_days of the
    universe per night and staggers naturally.

    The thinner sampling matters less here than it would elsewhere, because one observation carries
    its own 90-day trail (eps_7d_ago .. eps_90d_ago), so a ticker seen every few days still yields a
    dense revision series.

    Append-only and fail-soft: a ticker that errors is logged and skipped, never retried in a loop and
    never written as zeros. Returns the number of rows written."""
    if isinstance(tickers, str):
        tickers = [tickers]
    refresh_days = refresh_days if refresh_days is not None else PARAMS["estimates_refresh_days"]
    delay = PARAMS["fundamentals_fetch_delay_sec"]
    fetched_date = as_of_date or date.today().isoformat()
    storage.init_db(db_path)

    # Oldest-first by last observation, so every name is reached in turn and a never-seen ticker
    # (no rows at all) sorts ahead of every ticker that has been seen even once.
    conn = storage._connect(db_path)
    try:
        last_seen = dict(conn.execute(
            "SELECT ticker, MAX(fetched_date) FROM estimate_history GROUP BY ticker").fetchall())
    finally:
        conn.close()
    n = max(1, math.ceil(len(tickers) / refresh_days)) if tickers else 0
    ranked = sorted(tickers, key=lambda t: (last_seen.get(t) or "", t))
    to_fetch = ranked[:n]

    written, failed, skipped_empty = 0, [], 0
    for t in to_fetch:
        try:
            tk = yf.Ticker(t)
            rows = _estimate_rows_for_ticker(t, tk.eps_trend, tk.eps_revisions,
                                             fetched_date, _now_iso())
        except Exception as e:
            print(f"[data] estimates fetch failed for {t} ({e}) — skipped, no data invented")
            failed.append(t)
            time.sleep(delay)
            continue
        if rows:
            written += storage.upsert_estimate_rows(rows, db_path=db_path)
        else:
            # An ETF, or a name no analyst covers. Recorded as an explicit failed observation so it
            # sorts to the back of the queue instead of being retried first every single night.
            storage.upsert_estimate_rows([{
                "ticker": t, "fetched_date": fetched_date, "period": "none",
                "fetch_failed": 1, "timestamp_fetched": _now_iso()}], db_path=db_path)
            skipped_empty += 1
        time.sleep(delay)

    n_rows, n_tickers, first_seen, latest = storage.estimate_coverage(db_path=db_path)
    print(f"[data] estimates rolling — asked {len(to_fetch)} of {len(tickers)} names, wrote {written} "
          f"row(s), {skipped_empty} with no coverage, {len(failed)} failed")
    print(f"[data] estimate history now: {n_rows:,} rows across {n_tickers} tickers, "
          f"{first_seen or 'n/a'} .. {latest or 'n/a'} — this history cannot be backfilled later")
    if failed:
        print(f"[data] estimates failed tickers (skipped): {failed}")
    return written
