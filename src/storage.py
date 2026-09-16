"""SQLite persistence for market-warhorse.

Tables:
- price_history: cached daily OHLCV per ticker, the source of truth data.py reads/writes.
- feature_snapshots: one row per (run_date, ticker, model_version). Stage 1 only ever
  populates the raw-feature columns; the score/component columns are pre-declared here
  (nullable) so later stages can fill them in without an ALTER TABLE migration, keeping
  past snapshot rows comparable across model versions.
- fundamentals / earnings_dates: per-ticker caches with a TTL, refreshed on a rolling slice so a
  universe fetched together does not expire together and re-spike the request budget.
- edgar_facts / cik_map: the wide point-in-time XBRL store (every fact verbatim) and its ticker->CIK
  mapping, so a new fundamental factor is a config change rather than a re-ingest.
- journal: one rendered daily-log entry per (run_date, model_version).
- meta: small key/value markers (last successful run, per-CIK ingest freshness).

Runs in WAL mode so a reader (a progress query, a research script) cannot block the nightly writer.
"""

import os
import sqlite3
from datetime import datetime, timezone

from src.config import FUNDAMENTAL_FIELDS

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_data.db")

# Raw feature columns written by features.py in stage 1. Kept as a single list so the
# CREATE TABLE statement and any row-building code stay in sync.
RAW_FEATURE_COLUMNS = [
    # price/trend
    "latest_close", "SMA20", "SMA50", "SMA200",
    "close_vs_SMA20_pct", "close_vs_SMA50_pct", "close_vs_SMA200_pct",
    "SMA20_vs_SMA50_pct", "SMA50_vs_SMA200_pct",
    # momentum
    "return_1d", "return_5d", "return_10d", "return_20d",
    "return_60d", "return_120d", "return_252d", "return_252d_missing",
    # relative strength
    "benchmark_return_5d", "benchmark_return_20d", "benchmark_return_60d", "benchmark_return_120d",
    "relative_strength_5d", "relative_strength_20d", "relative_strength_60d", "relative_strength_120d",
    # volume/behavior
    "volume_ratio_20d", "volume_ratio_60d",
    "dollar_volume_20d", "illiquid_flag",
    "high_volume_up_days_20d", "high_volume_down_days_20d",
    "up_volume_vs_down_volume_20d",
    "close_position", "weak_close_flag", "strong_close_flag",
    # risk
    "ATR14", "ATR_pct", "volatility_20d", "volatility_60d", "downside_volatility_20d",
    "max_drawdown_20d", "max_drawdown_60d",
    "distance_from_52w_high_pct", "distance_from_52w_low_pct",
    # setup flags
    "near_20d_high", "near_60d_high", "not_extended_flag", "extended_flag",
    "pullback_above_SMA50", "failed_breakout_flag",
    # benchmark/market regime
    "benchmark_above_SMA20", "benchmark_above_SMA50", "benchmark_above_SMA200",
    "benchmark_volatility_20d", "benchmark_vol_high_flag",
    # earnings (best-effort, never invented)
    "days_until_earnings", "earnings_date_missing",
    # v0.2 fundamentals + short interest (live runs only; NULL + *_missing on backfill).
    # Raw values come straight from config.FUNDAMENTAL_FIELDS so this list can't drift.
    *FUNDAMENTAL_FIELDS,
    # Missing flags: one per sit-out factor family plus an overall flag. fundamentals_missing
    # is True whenever this row has no fundamentals at all (every backfill row, plus any live
    # ticker whose .info fetch failed). The per-family flags drive component sit-out.
    "fundamentals_missing", "value_missing", "quality_missing", "short_interest_missing",
    # v0.3 provenance: True when the ticker's value/quality was ranked cross-sectionally as a
    # fallback because its sector was too small for within-sector ranking (NULL on v0.1/v0.2 rows,
    # which don't sector-neutralize). Sector itself is NOT stored — it stays a scoring-time input
    # and a display-time join.
    "sector_rank_fallback",
]

# Cross-sectional percentile columns, computed once per run across all included tickers
# by scoring.compute_percentiles. The three risk fields and the 52w-high field already
# store the spec's *inverted*/cap-adjusted percentile, not a raw rank.
PERCENTILE_COLUMNS = [
    "return_5d_percentile", "return_10d_percentile", "return_20d_percentile",
    "return_60d_percentile", "return_120d_percentile", "return_252d_percentile",
    "relative_strength_5d_percentile", "relative_strength_20d_percentile",
    "relative_strength_60d_percentile", "relative_strength_120d_percentile",
    "volume_ratio_20d_percentile",
    "ATR_pct_percentile", "volatility_60d_percentile", "max_drawdown_60d_percentile",
    "distance_from_52w_high_adjusted_percentile",
    # v0.2 composite percentiles (mean of present sub-percentiles; NULL when the family sits out)
    "value_percentile", "quality_percentile", "short_interest_percentile",
]

# Score/component columns, populated starting in the scoring.py stage.
SCORE_COLUMNS = [
    "trend_component", "short_momentum_component", "momentum_component_20d",
    "medium_momentum_component", "long_momentum_component",
    "relative_strength_component_5d", "relative_strength_component_20d",
    "relative_strength_component_60d", "relative_strength_component_120d",
    "volume_behavior_component", "risk_component", "setup_component", "market_regime_component",
    # v0.2 components (NULL when their family sits out for the ticker)
    "value_component", "quality_component", "short_interest_component",
    "score_5d", "score_20d", "score_60d", "score_120d",
]


# How long a connection waits for a competing writer's lock before giving up (ms).
_BUSY_TIMEOUT_MS = 30000  # 30s — long enough to outlast another run's commit, not so long a real hang looks alive forever.


def _connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    # If another process holds a write lock (e.g. a manual catch-up run overlapping the
    # scheduled 6:30 run), wait up to this long for it to release instead of instantly
    # raising "database is locked" and killing the whole run. Infra plumbing, not a model
    # tunable — if you'd rather it live in config.PARAMS, it's a one-line move.
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    # WAL lets readers and a writer coexist. Under the default rollback journal a reader blocks the
    # writer and vice versa, so a long backfill could be killed outright by something as innocuous as
    # a progress query against the same file - which is exactly how the v0.5 backfill died at 351 of
    # 541 dates with "database is locked". journal_mode is persisted in the file, so this is a no-op
    # after the first call; it is set here so a fresh database gets it too.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path=DEFAULT_DB_PATH):
    """Create data/ and the database file/tables if they don't already exist."""
    conn = _connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                timestamp_fetched TEXT NOT NULL,
                UNIQUE(ticker, date)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history(ticker, date)")

        # v0.2 fundamentals cache: one LATEST row per ticker (point-in-time as of fetch — these
        # fields are not historical, so there is no date dimension here, unlike price_history).
        # Aggressively reused until stale (see data.fetch_fundamentals) to spare the rate limit.
        fundamental_cols_sql = ",\n                ".join(f"{c} REAL" for c in FUNDAMENTAL_FIELDS)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS fundamentals (
                ticker TEXT PRIMARY KEY,
                {fundamental_cols_sql},
                fetch_failed INTEGER NOT NULL DEFAULT 0,
                timestamp_fetched TEXT NOT NULL
            )
        """)

        # Next-earnings-date cache. Previously this was a raw yfinance call PER TICKER PER RUN with no
        # throttle and no cache — 519 uncached HTTP requests a night against Yahoo's ~360/hr soft limit,
        # and the single most likely way to get the IP blocked as the universe grows. Cached with a TTL
        # and refreshed on a rolling slice, exactly like `fundamentals`.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS earnings_dates (
                ticker TEXT PRIMARY KEY,
                earnings_date TEXT,
                fetch_failed INTEGER NOT NULL DEFAULT 0,
                timestamp_fetched TEXT NOT NULL
            )
        """)

        # ANALYST ESTIMATE HISTORY (accumulate-forward — that is the entire point of this table).
        #
        # Upward revisions to EPS estimates are the strongest documented anomaly this project has
        # never tested, and unlike price or filings THIS ONE CANNOT BE BOUGHT BACK for free. Yahoo
        # serves only the current snapshot, so the only way to own a history is to start writing one
        # down. Every night of delay is a night permanently missing from the sample.
        #
        # APPEND-ONLY, keyed on (ticker, fetched_date, period): re-running on the same day is
        # idempotent, but a later day NEVER overwrites an earlier observation. That is what makes the
        # table usable point-in-time — a feature for date D reads the newest row with
        # fetched_date <= D, and a row written afterwards cannot reach back into it.
        #
        # One fetch yields FIVE points per period, not one: eps_trend reports the estimate as it
        # stands now and as it stood 7/30/60/90 days ago, so a revision is computable from a single
        # observation instead of needing two nights of history. Those lagged values are Yahoo's
        # CURRENT account of the past and may be restated, which is exactly why `eps_current` is
        # stored alongside them — once this table holds 90 days of its OWN observations the two can
        # be compared, and the lagged columns checked rather than trusted.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS estimate_history (
                ticker TEXT NOT NULL,
                fetched_date TEXT NOT NULL,
                period TEXT NOT NULL,
                eps_current REAL,
                eps_7d_ago REAL,
                eps_30d_ago REAL,
                eps_60d_ago REAL,
                eps_90d_ago REAL,
                up_last_7d REAL,
                up_last_30d REAL,
                down_last_7d REAL,
                down_last_30d REAL,
                currency TEXT,
                fetch_failed INTEGER NOT NULL DEFAULT 0,
                timestamp_fetched TEXT NOT NULL,
                PRIMARY KEY (ticker, fetched_date, period)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_estimate_ticker_date "
                     "ON estimate_history(ticker, fetched_date)")

        feature_cols_sql = ",\n                ".join(f"{c} REAL" for c in RAW_FEATURE_COLUMNS)
        percentile_cols_sql = ",\n                ".join(f"{c} REAL" for c in PERCENTILE_COLUMNS)
        score_cols_sql = ",\n                ".join(f"{c} REAL" for c in SCORE_COLUMNS)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS feature_snapshots (
                run_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                benchmark TEXT NOT NULL,
                model_version TEXT NOT NULL,
                {feature_cols_sql},
                {percentile_cols_sql},
                {score_cols_sql},
                backfilled INTEGER NOT NULL DEFAULT 0,
                earnings_risk_unknown INTEGER NOT NULL DEFAULT 0,
                recovered INTEGER NOT NULL DEFAULT 0,
                fundamentals_as_of TEXT,
                timestamp_fetched TEXT NOT NULL,
                UNIQUE(run_date, ticker, model_version)
            )
        """)

        # Daily journal: one structured entry per (run_date, model_version). The entry_json
        # blob is the machine-readable record; output/DAILY_LOG.md is its human-readable mirror,
        # regenerated from this table. brief holds the optional Claude-API plain-English summary
        # (nullable — the journal never depends on the brief). Re-running a run_date REPLACES its
        # row (idempotent), never appends a duplicate.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS journal (
                run_date TEXT NOT NULL,
                model_version TEXT NOT NULL,
                backfilled INTEGER NOT NULL DEFAULT 0,
                entry_json TEXT NOT NULL,
                brief TEXT,
                timestamp_written TEXT NOT NULL,
                UNIQUE(run_date, model_version)
            )
        """)

        # Small key/value store for run-health metadata (e.g. "last_success"). Kept separate from
        # the journal so a health check never depends on parsing an entry, and so a clean-completion
        # marker exists even on a day that scored nothing new (weekend resolving to an existing date).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # v0.4 EDGAR: ticker -> CIK mapping (is_etf/benchmark rows carry no company fundamentals).
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cik_map (
                ticker TEXT PRIMARY KEY,
                cik TEXT,
                is_etf INTEGER NOT NULL DEFAULT 0,
                mapped_ok INTEGER NOT NULL DEFAULT 0,
                checked_at TEXT NOT NULL
            )
        """)

        # v0.4 EDGAR raw facts — deliberately GENERIC so it holds every us-gaap/dei XBRL fact a filer
        # reports, not just what value/quality needs (the "wide pipe"): future factors are a config +
        # re-derive, never a re-ingest. Stored verbatim; parsing/derivation happens on READ (the resolver).
        # PK dedupes a fact reported identically across filings; the same period reported by DIFFERENT
        # accessions is kept (originally-filed vs restatement) so the resolver can pick earliest-filed.
        # SEC Form 3/4/5 insider transactions, one row per reported transaction.
        #
        # `filed_date` is the POINT-IN-TIME GATE and is indexed for it: an insider has two business
        # days to report, so `trans_date` is knowledge the market did not have. Every read goes
        # through `load_insider_transactions(..., filed_on_or_before=D)`.
        #
        # The primary key is (accession, trans_sk, table_kind): the same surrogate key space is
        # reused between the derivative and non-derivative tables in SEC's own datasets, so the
        # table of origin has to be part of the key or one silently overwrites the other.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS insider_transactions (
                accession TEXT NOT NULL,
                trans_sk TEXT NOT NULL,
                table_kind TEXT NOT NULL,
                cik TEXT NOT NULL,
                -- OUR ticker, resolved from the CIK via cik_map. Never SEC's own symbol field:
                -- ISSUERTRADINGSYMBOL is free text typed by the filer and arrives as "(CALX)",
                -- "-", "BFA, BFB", "BIO BIO.B", "BRK.A". Joining on it silently returned ZERO
                -- insider rows for 35 of our names whose data was present all along. CIK is the
                -- only stable key, which is why the universe filter uses it too.
                ticker TEXT,
                sec_symbol TEXT,          -- kept verbatim for audit, never used to join
                filed_date TEXT NOT NULL,
                trans_date TEXT,
                doc_type TEXT,
                trans_code TEXT,
                acquired_disposed TEXT,
                shares REAL,
                price_per_share REAL,
                value_usd REAL,
                shares_owned_after REAL,
                owner_cik TEXT,
                owner_name TEXT,
                relationship TEXT,
                owner_title TEXT,
                is_director INTEGER NOT NULL DEFAULT 0,
                is_officer INTEGER NOT NULL DEFAULT 0,
                is_ten_pct_owner INTEGER NOT NULL DEFAULT 0,
                is_10b5_1 INTEGER NOT NULL DEFAULT 0,
                direct_indirect TEXT,
                ingested_at TEXT NOT NULL,
                -- Owner is DENORMALIZED onto the transaction rather than keyed, deliberately.
                -- 1,151 of 63,284 filings in a single quarter carry MULTIPLE reporting owners (up
                -- to 10). Keying by owner would store one copy of the same economic transaction per
                -- co-filer and multiply its share count by up to 10x in any aggregate. So the
                -- relationship flags are OR-ed across every owner on the filing and the transaction
                -- is stored once.
                PRIMARY KEY (accession, trans_sk, table_kind)
            )
        """)
        # SEC filing index: 8-K material events plus 10-K/10-Q dates, one row per filing.
        #
        # `acceptance_datetime` is stored VERBATIM and the trading-calendar roll is computed at read
        # time (`filings.effective_date`). Storing a derived "effective date" instead would leave
        # stale values behind the first time the calendar is corrected — and a gate that is a day
        # wrong is invisible in every output.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sec_filings (
                accession TEXT NOT NULL,
                cik TEXT NOT NULL,
                ticker TEXT,
                form TEXT NOT NULL,
                filed_date TEXT NOT NULL,
                acceptance_datetime TEXT,
                report_date TEXT,
                items TEXT,
                primary_doc TEXT,
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (accession, cik)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker_filed "
                     "ON sec_filings(ticker, filed_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sec_filings_form "
                     "ON sec_filings(form, filed_date)")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_ticker_filed "
                     "ON insider_transactions(ticker, filed_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_insider_filed "
                     "ON insider_transactions(filed_date)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS edgar_facts (
                cik TEXT NOT NULL,
                ticker TEXT,
                taxonomy TEXT NOT NULL,
                tag TEXT NOT NULL,
                unit TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT NOT NULL,
                fiscal_year INTEGER,
                fiscal_period TEXT,
                value REAL,
                form TEXT,
                accession TEXT NOT NULL,
                filed_date TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                -- period_start is IN the key: one filing reports the same tag/period_end for BOTH the
                -- 3-month quarterly and the year-to-date figure (different start). Omitting start would
                -- collide them and clobber the quarterly value TTM needs. Instant facts (balance sheet)
                -- carry start='' (never NULL) so the composite key stays well-defined.
                PRIMARY KEY (cik, tag, unit, period_start, period_end, accession)
            )
        """)
        # The resolver filters by ticker + filed_date <= D, then by tag — index for it.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edgar_ticker_tag_filed "
                     "ON edgar_facts(ticker, tag, filed_date)")

        # Idempotent migration: a feature_snapshots table created by an earlier stage
        # (e.g. stage 1, before PERCENTILE_COLUMNS existed) won't pick up new columns
        # from CREATE TABLE IF NOT EXISTS. Add any missing column without touching
        # existing rows, so past snapshots stay comparable (CLAUDE.md invariant #5).
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(feature_snapshots)").fetchall()}
        all_declared_cols = RAW_FEATURE_COLUMNS + PERCENTILE_COLUMNS + SCORE_COLUMNS
        for col in all_declared_cols:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE feature_snapshots ADD COLUMN {col} REAL")

        # Recovery-provenance columns (added after the initial schema, so they need explicit ALTERs —
        # the loop above only handles REAL columns). A `recovered` row is a LIVE snapshot (backfilled=0)
        # reconstructed point-in-time for a MISSED trading day; its price/volume features are strictly
        # as-of that day, but its fundamentals were stamped from a later fetch (`fundamentals_as_of`) —
        # flagged so a stale-fundamentals row is never mistaken for a true point-in-time one and can be
        # excluded from the fundamental-factor IC (no-lookahead, CLAUDE.md #1).
        if "recovered" not in existing_cols:
            conn.execute("ALTER TABLE feature_snapshots ADD COLUMN recovered INTEGER NOT NULL DEFAULT 0")
        if "fundamentals_as_of" not in existing_cols:
            conn.execute("ALTER TABLE feature_snapshots ADD COLUMN fundamentals_as_of TEXT")
        # v0.4: are this row's FUNDAMENTALS genuinely point-in-time? `recovered` alone stopped being a
        # sufficient proxy once EDGAR arrived. A v0.2/v0.3 recovered row carries fundamentals stamped
        # from a LATER fetch (not PIT), but a v0.4 row reconstructs them from filings gated on
        # filed_date <= D — genuinely PIT even on a recovered day. Downstream exclusion keys off THIS,
        # so EDGAR rows are correctly INCLUDED in the fundamental-factor IC. Default 0 = "not PIT",
        # which is the safe reading for every pre-existing row (they were all yfinance-sourced).
        if "fundamentals_pit" not in existing_cols:
            conn.execute("ALTER TABLE feature_snapshots ADD COLUMN fundamentals_pit INTEGER NOT NULL DEFAULT 0")

        conn.commit()
    finally:
        conn.close()
    return db_path


def get_cached_dates(ticker, db_path=DEFAULT_DB_PATH):
    """Return the sorted list of date strings ('YYYY-MM-DD') already cached for ticker."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT date FROM price_history WHERE ticker = ? ORDER BY date ASC", (ticker,)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def upsert_price_rows(rows, db_path=DEFAULT_DB_PATH):
    """rows: iterable of dicts with keys ticker, date, open, high, low, close, volume, timestamp_fetched."""
    if not rows:
        return 0
    conn = _connect(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO price_history (ticker, date, open, high, low, close, volume, timestamp_fetched)
            VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :timestamp_fetched)
            ON CONFLICT(ticker, date) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume,
                timestamp_fetched=excluded.timestamp_fetched
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_cached_fundamentals(ticker, db_path=DEFAULT_DB_PATH):
    """Return the cached fundamentals row for ticker as a dict (including timestamp_fetched and
    fetch_failed), or None if the ticker has never been fetched. Never invents values — a field
    absent at fetch time is stored as NULL and comes back as None."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM fundamentals WHERE ticker = ?", (ticker,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def get_cached_earnings_date(ticker, db_path=DEFAULT_DB_PATH):
    """Cached next-earnings row for ticker as a dict, or None if never fetched. A row with
    earnings_date NULL and fetch_failed=1 means "we asked and got nothing" — distinct from
    "never asked", which is what None means. Never invents a date."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM earnings_dates WHERE ticker = ?", (ticker,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def upsert_earnings_date(ticker, earnings_date, timestamp_fetched, fetch_failed=False,
                         db_path=DEFAULT_DB_PATH):
    """Write/overwrite the single cached next-earnings row for ticker."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO earnings_dates (ticker, earnings_date, fetch_failed, timestamp_fetched) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(ticker) DO UPDATE SET "
            "earnings_date=excluded.earnings_date, fetch_failed=excluded.fetch_failed, "
            "timestamp_fetched=excluded.timestamp_fetched",
            (ticker, earnings_date, 1 if fetch_failed else 0, timestamp_fetched))
        conn.commit()
    finally:
        conn.close()


def upsert_fundamentals(ticker, fields, timestamp_fetched, fetch_failed=False, db_path=DEFAULT_DB_PATH):
    """fields: dict of {fundamental_field -> value or None}. Writes/overwrites the single latest
    row for ticker. fetch_failed records that the most recent attempt returned nothing (so the
    caller can distinguish 'fetched, genuinely has no data' from 'never reached')."""
    all_cols = ["ticker"] + FUNDAMENTAL_FIELDS + ["fetch_failed", "timestamp_fetched"]
    full_row = {c: fields.get(c) for c in FUNDAMENTAL_FIELDS}
    full_row.update({
        "ticker": ticker,
        "fetch_failed": 1 if fetch_failed else 0,
        "timestamp_fetched": timestamp_fetched,
    })
    placeholders = ", ".join(f":{c}" for c in all_cols)
    col_list = ", ".join(all_cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in all_cols if c != "ticker")
    conn = _connect(db_path)
    try:
        conn.execute(
            f"INSERT INTO fundamentals ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT(ticker) DO UPDATE SET {update_clause}",
            full_row,
        )
        conn.commit()
    finally:
        conn.close()


def load_price_history(ticker, db_path=DEFAULT_DB_PATH):
    """Return list of dicts (date, open, high, low, close, volume) sorted by date ascending."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM price_history "
            "WHERE ticker = ? ORDER BY date ASC",
            (ticker,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def latest_trading_date(db_path=DEFAULT_DB_PATH, calendar_ticker="SPY"):
    """The most recent COMPLETED trading session, derived from DATA not the clock: MAX(date) of the
    calendar ticker (SPY — fetched every run and trading every NYSE session). Yahoo only publishes a
    bar once a session has completed, so a catch-up run at 7am before the open sees yesterday's bar as
    the max (records as the prior trading day, never today), and a weekend/holiday run sees the last
    real session (no phantom date). None if the calendar ticker isn't cached yet."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(date) FROM price_history WHERE ticker = ?", (calendar_ticker,)
        ).fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def set_meta(key, value, db_path=DEFAULT_DB_PATH):
    """Write a run-health metadata value (upsert). `value` is a string (callers JSON-encode dicts)."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO meta (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_meta(key, db_path=DEFAULT_DB_PATH):
    """Read a meta value string, or None if the key was never written."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# --- v0.4 EDGAR accessors ---------------------------------------------------------------------

def upsert_cik_map_rows(rows, db_path=DEFAULT_DB_PATH):
    """rows: iterable of dicts {ticker, cik, is_etf, mapped_ok, checked_at}."""
    rows = list(rows)
    if not rows:
        return 0
    conn = _connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO cik_map (ticker, cik, is_etf, mapped_ok, checked_at) "
            "VALUES (:ticker, :cik, :is_etf, :mapped_ok, :checked_at) "
            "ON CONFLICT(ticker) DO UPDATE SET cik=excluded.cik, is_etf=excluded.is_etf, "
            "mapped_ok=excluded.mapped_ok, checked_at=excluded.checked_at",
            [{k: r.get(k) for k in ("ticker", "cik", "is_etf", "mapped_ok", "checked_at")} for r in rows],
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def load_cik_map(db_path=DEFAULT_DB_PATH):
    """Return {ticker -> {cik, is_etf, mapped_ok, checked_at}} for every mapped ticker."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM cik_map")}
    finally:
        conn.close()


def get_cik(ticker, db_path=DEFAULT_DB_PATH):
    """The CIK for a mappable, non-ETF ticker, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT cik FROM cik_map WHERE ticker=? AND mapped_ok=1 AND is_etf=0", (ticker,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


_EDGAR_FACT_COLS = ["cik", "ticker", "taxonomy", "tag", "unit", "period_start", "period_end",
                    "fiscal_year", "fiscal_period", "value", "form", "accession", "filed_date",
                    "ingested_at"]


def upsert_edgar_facts(rows, db_path=DEFAULT_DB_PATH):
    """Bulk insert-or-replace raw EDGAR facts. rows: iterable of dicts with the edgar_facts columns.
    Stored verbatim — parsing/derivation happens on read (the resolver)."""
    rows = list(rows)
    if not rows:
        return 0
    placeholders = ", ".join(f":{c}" for c in _EDGAR_FACT_COLS)
    conn = _connect(db_path)
    try:
        conn.executemany(
            f"INSERT OR REPLACE INTO edgar_facts ({', '.join(_EDGAR_FACT_COLS)}) VALUES ({placeholders})",
            [{c: r.get(c) for c in _EDGAR_FACT_COLS} for r in rows],
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def load_edgar_facts(ticker, filed_on_or_before=None, tags=None, db_path=DEFAULT_DB_PATH):
    """Raw edgar_facts rows for a ticker (list of dicts), optionally gated to filed_date <= a date and
    restricted to a set of tags. This is the resolver's read path — the filed-date gate (the no-lookahead
    rule for fundamentals) is applied here in SQL so a leak can't slip past."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql, params = "SELECT * FROM edgar_facts WHERE ticker = ?", [ticker]
        if filed_on_or_before is not None:
            sql += " AND filed_date <= ?"
            params.append(filed_on_or_before)
        if tags:
            sql += f" AND tag IN ({', '.join('?' for _ in tags)})"
            params.extend(tags)
        return [dict(r) for r in conn.execute(sql, params)]
    finally:
        conn.close()


def count_edgar_facts(ticker=None, db_path=DEFAULT_DB_PATH):
    """Row count in edgar_facts (optionally for one ticker) — for ingest verification."""
    conn = _connect(db_path)
    try:
        if ticker is not None:
            return conn.execute("SELECT COUNT(*) FROM edgar_facts WHERE ticker=?", (ticker,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM edgar_facts").fetchone()[0]
    finally:
        conn.close()


def get_backfilled_dates(model_version, db_path=DEFAULT_DB_PATH):
    """Distinct run_dates already written for a model_version. Lets a long backfill resume where it
    stopped instead of redoing hours of completed work."""
    conn = _connect(db_path)
    try:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT run_date FROM feature_snapshots WHERE model_version = ?",
            (model_version,))]
    finally:
        conn.close()


def load_all_snapshots(db_path=DEFAULT_DB_PATH, model_version=None):
    """Return every feature_snapshots row as a list of dicts, ordered by (run_date, ticker).
    Backs both the CSV exports and evaluation.py — always queried fresh from the DB
    (the source of truth), never accumulated in memory across runs."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        if model_version is not None:
            rows = conn.execute(
                "SELECT * FROM feature_snapshots WHERE model_version = ? ORDER BY run_date, ticker",
                (model_version,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM feature_snapshots ORDER BY run_date, ticker"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_snapshots_for_date(model_version, run_date, db_path=DEFAULT_DB_PATH):
    """Every feature_snapshots row for one (model_version, run_date), as dicts ordered by ticker.
    Used by the daily journal's Section 1 (today's rankings): it needs per-ticker columns
    (score, days_until_earnings) for a single date WITHOUT loading the whole table or requiring
    price history to exist (unlike evaluation.evaluate_all_snapshots, which joins forward returns)."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM feature_snapshots WHERE model_version = ? AND run_date = ? ORDER BY ticker",
            (model_version, run_date),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_journal_entry(run_date, model_version, backfilled, entry_json, timestamp_written,
                         brief=None, db_path=DEFAULT_DB_PATH):
    """Insert or REPLACE the journal row for (run_date, model_version) — re-running a date
    overwrites its entry rather than appending (idempotency, per spec). brief is written only
    when provided; passing None on a re-journal leaves any existing brief untouched via COALESCE
    so the journal step never clobbers a brief the brief step wrote."""
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO journal (run_date, model_version, backfilled, entry_json, brief, timestamp_written)
            VALUES (:run_date, :model_version, :backfilled, :entry_json, :brief, :timestamp_written)
            ON CONFLICT(run_date, model_version) DO UPDATE SET
                backfilled=excluded.backfilled,
                entry_json=excluded.entry_json,
                brief=COALESCE(excluded.brief, journal.brief),
                timestamp_written=excluded.timestamp_written
            """,
            {"run_date": run_date, "model_version": model_version,
             "backfilled": 1 if backfilled else 0, "entry_json": entry_json,
             "brief": brief, "timestamp_written": timestamp_written},
        )
        conn.commit()
    finally:
        conn.close()


def update_journal_brief(run_date, model_version, brief, db_path=DEFAULT_DB_PATH):
    """Attach (or replace) the AI brief on an already-written journal row. No-op if the row
    doesn't exist yet — the journal is always written first, so that shouldn't happen."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE journal SET brief = ? WHERE run_date = ? AND model_version = ?",
            (brief, run_date, model_version),
        )
        conn.commit()
    finally:
        conn.close()


def get_journal_entry(run_date, model_version, db_path=DEFAULT_DB_PATH):
    """Return the journal row dict for (run_date, model_version), or None."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM journal WHERE run_date = ? AND model_version = ?",
            (run_date, model_version),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def load_all_journal_entries(db_path=DEFAULT_DB_PATH):
    """Every journal row, newest run_date first — the source of truth DAILY_LOG.md regenerates
    from, so the file and the table can never drift."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM journal ORDER BY run_date DESC, model_version DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_live_run_dates(model_version, db_path=DEFAULT_DB_PATH):
    """Sorted (ascending) distinct run_dates for model_version where backfilled=0 — the live
    trading days accumulated for that version. Used for top-10 movement and the v0.2 live-day
    counter."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT run_date FROM feature_snapshots "
            "WHERE model_version = ? AND backfilled = 0 ORDER BY run_date ASC",
            (model_version,),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_score_map(model_version, run_date, column="score_20d", db_path=DEFAULT_DB_PATH):
    """{ticker -> score} for one run, skipping rows whose score is NULL. Used to compute the
    top-10 and single-day movers by joining two run_dates on ticker (never by row position)."""
    if column not in SCORE_COLUMNS:  # column is interpolated into SQL — allow only known columns
        raise ValueError(f"get_score_map: unknown score column {column!r}")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f"SELECT ticker, {column} FROM feature_snapshots "
            f"WHERE model_version = ? AND run_date = ? AND {column} IS NOT NULL",
            (model_version, run_date),
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


ESTIMATE_COLUMNS = ["eps_current", "eps_7d_ago", "eps_30d_ago", "eps_60d_ago", "eps_90d_ago",
                    "up_last_7d", "up_last_30d", "down_last_7d", "down_last_30d"]


def upsert_estimate_rows(rows, db_path=DEFAULT_DB_PATH):
    """Append estimate observations. Keyed on (ticker, fetched_date, period), so re-running a day is
    idempotent while a later day can never overwrite an earlier observation.

    A missing field is written as NULL, never 0 — "no analyst revised" and "we failed to ask" are
    different facts, and conflating them is how a data gap becomes a signal (invariant #2)."""
    if not rows:
        return 0
    cols = (["ticker", "fetched_date", "period"] + ESTIMATE_COLUMNS
            + ["currency", "fetch_failed", "timestamp_fetched"])
    conn = _connect(db_path)
    try:
        conn.executemany(
            f"INSERT OR REPLACE INTO estimate_history ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)})",
            [tuple(r.get(c) for c in cols) for r in rows])
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def get_estimates_as_of(ticker, as_of_date, db_path=DEFAULT_DB_PATH):
    """The freshest estimate observation per period that EXISTED on as_of_date.

    THE NO-LOOKAHEAD GATE for estimates, enforced in SQL exactly as `load_edgar_facts` does for
    filings: `fetched_date <= as_of_date`, newest first, one row per period. An observation written
    tomorrow cannot appear in a feature computed for today, no matter what the caller does.

    Returns {period: row-dict}; empty when nothing had been observed yet for this ticker."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM estimate_history WHERE ticker = ? AND fetched_date <= ? "
            "ORDER BY fetched_date DESC", (ticker, as_of_date)).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["period"], dict(r))     # first seen == newest, since sorted DESC
        return out
    finally:
        conn.close()


def estimate_coverage(db_path=DEFAULT_DB_PATH):
    """(n_rows, n_tickers, earliest_fetched_date, latest_fetched_date) — how much history the
    accumulate-forward table has actually managed to collect. Reported by --status so the owner can
    see the sample growing, since its whole value is that it cannot be recovered later."""
    conn = _connect(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(fetched_date), MAX(fetched_date) "
            "FROM estimate_history WHERE fetch_failed = 0").fetchone()
    finally:
        conn.close()


def latest_snapshot_date(model_version, db_path=DEFAULT_DB_PATH):
    """The most recent run_date holding a snapshot for this model_version, or None.

    Used to decide whether a version is genuinely EXHAUSTED — whether its newest snapshot has
    already matured at the longest horizon — rather than merely listed as frozen."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(run_date) FROM feature_snapshots WHERE model_version = ?",
            (model_version,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def list_model_versions(db_path=DEFAULT_DB_PATH):
    """Distinct model_version strings present in feature_snapshots, sorted ascending. Lets the
    evaluation build one side-by-side report across every version that has been run (e.g. v0.1
    baseline next to v0.2), without hardcoding the list."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT model_version FROM feature_snapshots ORDER BY model_version ASC"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _snapshot_columns():
    """The full ordered column list every snapshot write uses. One definition so the single-row and
    batch writers can never disagree about column order or membership."""
    return (["run_date", "ticker", "benchmark", "model_version"] + RAW_FEATURE_COLUMNS
            + PERCENTILE_COLUMNS + SCORE_COLUMNS
            + ["backfilled", "earnings_risk_unknown", "recovered", "fundamentals_as_of",
               "fundamentals_pit", "timestamp_fetched"])


def _normalized_snapshot_row(row, all_cols):
    """Project a caller's dict onto the full column list, filling absent columns with NULL.
    `recovered` / `fundamentals_pit` are NOT NULL: the column DEFAULT only applies to OMITTED columns,
    but we always list them, so an absent value would pass explicit NULL and fail the constraint.
    Coerce to 0/1 here so every caller (backfill/live rows that never set them) is safe.
    fundamentals_as_of stays nullable."""
    full_row = {col: row.get(col) for col in all_cols}
    full_row["recovered"] = 1 if full_row.get("recovered") else 0
    full_row["fundamentals_pit"] = 1 if full_row.get("fundamentals_pit") else 0
    return full_row


def _snapshot_upsert_sql(all_cols):
    placeholders = ", ".join(f":{c}" for c in all_cols)
    col_list = ", ".join(all_cols)
    update_clause = ", ".join(f"{c}=excluded.{c}" for c in all_cols
                              if c not in ("run_date", "ticker", "model_version"))
    return (f"INSERT INTO feature_snapshots ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT(run_date, ticker, model_version) DO UPDATE SET {update_clause}")


def upsert_feature_snapshots(rows, db_path=DEFAULT_DB_PATH):
    """Write MANY snapshot rows in ONE transaction on ONE connection.

    The single-row writer opens a connection, commits (an fsync), and closes it per row. That is fine
    for a handful of rows and ruinous for a backfill: ~500 tickers x ~533 dates = ~266,000 fsyncs
    against a 5 GB database. Measured, the v0.4 backfill ran at 30% CPU — I/O-bound, on track for
    ~24 hours. Batching per date turns 500 commits into 1.

    Same SQL and same idempotency as `upsert_feature_snapshot` (INSERT OR REPLACE semantics keyed on
    run_date+ticker+model_version), so a restarted backfill overwrites its own partial work safely."""
    rows = list(rows)
    if not rows:
        return 0
    all_cols = _snapshot_columns()
    payload = [_normalized_snapshot_row(r, all_cols) for r in rows]
    conn = _connect(db_path)
    try:
        conn.executemany(_snapshot_upsert_sql(all_cols), payload)
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def upsert_feature_snapshot(row, db_path=DEFAULT_DB_PATH):
    """row: dict containing run_date, ticker, benchmark, model_version, timestamp_fetched,
    backfilled, earnings_risk_unknown, plus any subset of RAW_FEATURE_COLUMNS/SCORE_COLUMNS.
    Missing optional columns are written as NULL.
    """
    all_cols = _snapshot_columns()
    conn = _connect(db_path)
    try:
        conn.execute(_snapshot_upsert_sql(all_cols), _normalized_snapshot_row(row, all_cols))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SEC Form 3/4/5 insider transactions
# ---------------------------------------------------------------------------

INSIDER_COLUMNS = [
    "accession", "trans_sk", "table_kind", "cik", "ticker", "sec_symbol", "filed_date", "trans_date",
    "doc_type", "trans_code", "acquired_disposed", "shares", "price_per_share", "value_usd",
    "shares_owned_after", "owner_cik", "owner_name", "relationship", "owner_title",
    "is_director", "is_officer", "is_ten_pct_owner", "is_10b5_1", "direct_indirect",
    "ingested_at",
]


def upsert_insider_transactions(rows, db_path=DEFAULT_DB_PATH):
    """Batch-write insider transaction rows. Idempotent on the primary key, so re-parsing a
    quarter's dataset is safe and a partially-ingested quarter can simply be re-run."""
    if not rows:
        return 0
    cols = INSIDER_COLUMNS
    sql = (f"INSERT OR REPLACE INTO insider_transactions ({', '.join(cols)}) "
           f"VALUES ({', '.join('?' for _ in cols)})")
    payload = [tuple(r.get(c) for c in cols) for r in rows]
    conn = _connect(db_path)
    try:
        conn.executemany(sql, payload)
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def load_insider_transactions(ticker=None, filed_on_or_before=None, filed_on_or_after=None,
                              codes=None, db_path=DEFAULT_DB_PATH):
    """Insider rows, optionally gated to what had been FILED by a given date.

    `filed_on_or_before` is the point-in-time gate and the only correct way to read this table for
    anything that feeds a score. It is deliberately a required-feeling keyword rather than a default
    of "everything": a caller that forgets it gets the whole history, which is why every consumer in
    this project passes it explicitly and `tests/test_insider.py` asserts the gate directly."""
    where, params = [], []
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    if filed_on_or_before:
        where.append("filed_date <= ?")
        params.append(filed_on_or_before)
    if filed_on_or_after:
        where.append("filed_date >= ?")
        params.append(filed_on_or_after)
    if codes:
        where.append("trans_code IN (%s)" % ", ".join("?" for _ in codes))
        params.extend(list(codes))
    sql = "SELECT * FROM insider_transactions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY filed_date, accession"
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def insider_coverage(db_path=DEFAULT_DB_PATH):
    """(min_filed_date, max_filed_date, n_rows, n_tickers) actually present in the store.

    Read from the DATA rather than from config, because the honest answer to "do we know whether
    there was insider buying on 2026-07-01?" is decided by what was ingested, not by what was
    intended. Anything past `max_filed_date` is UNKNOWN and must never be reported as zero
    activity — CLAUDE.md invariant #2."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT MIN(filed_date), MAX(filed_date), COUNT(*), COUNT(DISTINCT ticker) "
            "FROM insider_transactions").fetchone()
        return {"first_filed_date": row[0], "last_filed_date": row[1],
                "n_rows": row[2], "n_tickers": row[3]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SEC filing index (8-K / 10-K / 10-Q)
# ---------------------------------------------------------------------------

SEC_FILING_COLUMNS = ["accession", "cik", "ticker", "form", "filed_date",
                      "acceptance_datetime", "report_date", "items", "primary_doc",
                      "ingested_at"]


def upsert_sec_filings(rows, db_path=DEFAULT_DB_PATH):
    """Batch-write filing index rows. Idempotent on (accession, cik), so a company can be re-fetched
    freely — which matters because this source is refreshed, not frozen."""
    if not rows:
        return 0
    cols = SEC_FILING_COLUMNS
    sql = (f"INSERT OR REPLACE INTO sec_filings ({', '.join(cols)}) "
           f"VALUES ({', '.join('?' for _ in cols)})")
    conn = _connect(db_path)
    try:
        conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def load_sec_filings(ticker=None, forms=None, filed_on_or_before=None, filed_on_or_after=None,
                     db_path=DEFAULT_DB_PATH):
    """Filing rows, optionally gated by form and filing date.

    NOTE: `filed_on_or_before` gates on the FILING date, which is necessary but not sufficient for
    point-in-time correctness — a filing accepted after the close is stamped with that day's date
    yet was not actionable until the next session. `filings.effective_date` applies that roll, and
    every feature goes through it."""
    where, params = [], []
    if ticker:
        where.append("ticker = ?")
        params.append(ticker)
    if forms:
        where.append("form IN (%s)" % ", ".join("?" for _ in forms))
        params.extend(list(forms))
    if filed_on_or_before:
        where.append("filed_date <= ?")
        params.append(filed_on_or_before)
    if filed_on_or_after:
        where.append("filed_date >= ?")
        params.append(filed_on_or_after)
    sql = "SELECT * FROM sec_filings"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY filed_date, accession"
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


SEC_FILINGS_INGEST_MARKER = "sec_filings_ingested_through"


def sec_filings_coverage(db_path=DEFAULT_DB_PATH):
    """What the filing store actually holds, and how current it is.

    `ingested_through` is written by a COMPLETED ingest and is the value features gate on. The
    obvious alternative — MAX(filed_date) across the table — is a bad coverage signal here: with
    1,500 companies somebody files every business day, so a run that fetched 3 companies and then
    died would still look current. It is returned as `last_filed_date` for information, but it is
    not what decides whether a date is knowable."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT MIN(filed_date), MAX(filed_date), COUNT(*), COUNT(DISTINCT ticker) "
            "FROM sec_filings").fetchone()
        marker = conn.execute("SELECT value FROM meta WHERE key = ?",
                              (SEC_FILINGS_INGEST_MARKER,)).fetchone()
        return {"first_filed_date": row[0], "last_filed_date": row[1],
                "n_rows": row[2], "n_tickers": row[3],
                "ingested_through": marker[0] if marker else None}
    finally:
        conn.close()


def live_snapshot_counts(model_version, db_path=DEFAULT_DB_PATH):
    """[(run_date, n_tickers), ...] ascending, for LIVE rows only.

    Backfilled rows are excluded deliberately: a backfill covers whatever the universe was on that
    date and is not comparable to a live run's coverage."""
    conn = _connect(db_path)
    try:
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT run_date, COUNT(*) FROM feature_snapshots "
            "WHERE model_version = ? AND backfilled = 0 GROUP BY run_date ORDER BY run_date",
            (model_version,))]
    finally:
        conn.close()
