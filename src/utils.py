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
