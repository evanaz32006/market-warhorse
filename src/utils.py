"""Data-integrity checks run right after data.fetch_price_history, before any feature or
score computation. Fail-loud per CLAUDE.md: warn clearly, never silently swallow a problem.
Other validation buckets from the spec (feature NaN logging, component-range/NaN checks)
already live inline in features.py and scoring.py respectively.
"""


def check_duplicate_price_rows(histories):
    """histories: dict[ticker -> list of {date, open, high, low, close, volume}].
    Warn if any ticker's cached history has more than one row for the same date."""
    for ticker, rows in histories.items():
        dates = [row["date"] for row in rows]
        dupes = {d for d in dates if dates.count(d) > 1}
        if dupes:
            print(f"[utils] WARNING: {ticker} has duplicate price rows for date(s): {sorted(dupes)}")


def check_benchmark_coverage(watchlist_df, histories):
    """Warn if any watchlist ticker's assigned benchmark has no cached history at all."""
    for _, row in watchlist_df.iterrows():
        ticker, benchmark = row["ticker"], row["benchmark"]
        if not histories.get(benchmark):
            print(f"[utils] WARNING: {ticker}'s benchmark {benchmark} has no cached price history")


def check_sufficient_history(ticker, history, window=252):
    """Warn if a ticker has fewer than `window` bars — flags a fetch problem distinct from
    the ordinary 'too new to have 252d of return history yet' case, since the caller
    decides whether to call this only for tickers expected to be long-listed."""
    if len(history) < window:
        print(f"[utils] WARNING: {ticker} has only {len(history)} cached bars, "
              f"fewer than the {window}-bar window some features require")


def check_calendar_gaps(histories, benchmarks=(), calendar_ticker="SPY", max_report=6):
    """Warn when a ticker is missing sessions the calendar ticker traded INSIDE its own span.

    The incremental fetcher resumes from `cached_dates[-1]` (data.fetch_price_history), so it only
    ever extends the FRONT of a series. A hole behind that frontier is invisible to it forever — no
    retry, no error, nothing in the logs.

    That is not hypothetical. IJH and IJR were each missing exactly two sessions, 2026-07-21 and
    2026-07-31. Two bars. The consequence was that every forward window spanning them came up two
    sessions short, so `_forward_return` hit its `idx + n >= len` guardrail and returned None — and
    since IJH/IJR are the benchmarks for every mid- and small-cap name, **two thirds of the universe
    silently vanished from the 60d and 120d hit rates** while the log kept reporting them as if they
    covered everything.

    A gap in a BENCHMARK is therefore reported separately and much louder than a gap in one name: it
    invalidates every ticker that measures itself against it, not just itself.
    """
    calendar = [r["date"] for r in histories.get(calendar_ticker, [])]
    if not calendar:
        return []
    benchmarks = set(benchmarks or ())
    found = []
    for ticker, rows in histories.items():
        if not rows:
            continue
        have = {r["date"] for r in rows}
        first, last = min(have), max(have)
        # Only sessions inside the ticker's OWN span count. A name listed in 2025 legitimately has
        # no 2024 bars, and flagging that would bury the real gaps in noise.
        missing = [d for d in calendar if first <= d <= last and d not in have]
        if missing:
            found.append((ticker, missing))

    for ticker, missing in sorted(found, key=lambda x: (x[0] not in benchmarks, -len(x[1]))):
        shown = ", ".join(missing[:max_report])
        more = f" (+{len(missing) - max_report} more)" if len(missing) > max_report else ""
        if ticker in benchmarks:
            print(f"[utils] BENCHMARK GAP: {ticker} is missing {len(missing)} session(s) inside its "
                  f"own span: {shown}{more}. Every ticker benchmarked against it loses any forward "
                  f"window spanning these dates — refetch before trusting horizon statistics.")
        else:
            print(f"[utils] WARNING: {ticker} is missing {len(missing)} cached session(s) inside "
                  f"its own span: {shown}{more}")
    return found
