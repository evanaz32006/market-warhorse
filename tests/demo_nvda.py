"""Manual stage-1 demo: fetch NVDA + its benchmark SMH through the real yfinance/SQLite
path, compute the full raw-feature set as of the latest cached date, persist a snapshot,
and print everything for visual inspection.

Run twice in a row: the second run's fetch summary should show NVDA/SMH served from
cache (no fresh network calls), proving the incremental-fetch path works.
"""

import json
from datetime import datetime, date, timezone

from src import data, features, storage
from src.config import PARAMS

TICKER = "NVDA"
BENCHMARK = "SMH"


def main():
    db_path = storage.DEFAULT_DB_PATH
    storage.init_db(db_path)

    summary = data.fetch_price_history([TICKER, BENCHMARK], db_path=db_path)
    print(f"[demo] fetch summary: {summary}")

    ticker_history = storage.load_price_history(TICKER, db_path=db_path)
    benchmark_history = storage.load_price_history(BENCHMARK, db_path=db_path)
    if not ticker_history or not benchmark_history:
        print("[demo] no cached price history available — fetch must have failed for both tickers.")
        return

    as_of_date = ticker_history[-1]["date"]
    print(f"[demo] computing features for {TICKER} (benchmark {BENCHMARK}) as of {as_of_date}")

    feature_row = features.compute_features(TICKER, BENCHMARK, as_of_date, ticker_history, benchmark_history)

    earnings_date, earnings_missing = data.fetch_next_earnings_date(TICKER)
    days_until_earnings = None
    if earnings_date is not None:
        ed = earnings_date.date() if hasattr(earnings_date, "date") else earnings_date
        if isinstance(ed, date):
            days_until_earnings = (ed - date.today()).days

    snapshot_row = dict(feature_row)
    snapshot_row.update({
        "run_date": as_of_date,
        "ticker": TICKER,
        "benchmark": BENCHMARK,
        "model_version": PARAMS["model_version"],
        "backfilled": False,
        "earnings_risk_unknown": earnings_missing,
        "days_until_earnings": days_until_earnings,
        "earnings_date_missing": earnings_missing,
        "timestamp_fetched": datetime.now(timezone.utc).isoformat(),
    })
    storage.upsert_feature_snapshot(snapshot_row, db_path=db_path)

    print(f"[demo] wrote feature_snapshots row for ({as_of_date}, {TICKER}, {PARAMS['model_version']})")
    print("[demo] computed features:")
    print(json.dumps(feature_row, indent=2, default=str))

    sma200 = feature_row.get("SMA200")
    latest_close = feature_row.get("latest_close")
    print(f"[demo] sanity check: latest_close={latest_close}, SMA200={sma200}, "
          f"close_vs_SMA200_pct={feature_row.get('close_vs_SMA200_pct')}")


if __name__ == "__main__":
    main()
