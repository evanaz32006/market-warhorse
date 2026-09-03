"""Fetch-layer tests. Focus: the incremental price fetch batches tickers that share a missing-tail
start date (the daily-run wall-clock lever) instead of one throttled call per ticker."""
import math
import re
from datetime import datetime, timedelta, timezone

from src import data, storage
from src.config import FUNDAMENTAL_FIELDS, PARAMS


def _fake_yf(fetched, raise_for=frozenset()):
    """A stand-in for yfinance.Ticker that records which tickers were fetched and can be told to raise
    on `.info` for specific tickers (to exercise the fail-soft path)."""
    class _T:
        def __init__(self, t):
            self.t = t
            fetched.append(t)

        @property
        def info(self):
            if self.t in raise_for:
                raise RuntimeError("boom .info")
            return {"trailingPE": 10.0, "profitMargins": 0.2, "shortPercentOfFloat": 0.03}
    return _T


def _seed_fund(db, ticker, age_days):
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    storage.upsert_fundamentals(ticker, {f: 3.0 for f in FUNDAMENTAL_FIELDS}, ts, db_path=db)


def _seed(db, tickers, last_date):
    for t in tickers:
        storage.upsert_price_rows([{"ticker": t, "date": last_date, "open": 1, "high": 1,
                                    "low": 1, "close": 1, "volume": 1, "timestamp_fetched": "t"}], db_path=db)


def test_incremental_fetch_batches_by_shared_start(monkeypatch, tmp_path):
    db = str(tmp_path / "d.db")
    storage.init_db(db)
    tickers = [f"T{i}" for i in range(20)]
    old = (datetime.now(timezone.utc).date() - timedelta(days=3)).isoformat()
    _seed(db, tickers, old)                       # all cached to the same date -> all share one start

    calls = []
    monkeypatch.setattr(data, "_download_with_retry",
                        lambda batch, start=None, end=None, period=None: (calls.append(list(batch)), "FRAME")[1])
    monkeypatch.setattr(data, "_rows_from_download",
                        lambda df, t: [{"ticker": t, "date": "2026-07-20", "open": 1, "high": 1,
                                        "low": 1, "close": 1, "volume": 1, "timestamp_fetched": "t"}])
    monkeypatch.setitem(PARAMS, "yfinance_batch_delay_sec", 0)

    summary = data.fetch_price_history(tickers, db_path=db)

    bs = PARAMS["yfinance_batch_size"]
    expected_batches = (len(tickers) + bs - 1) // bs
    assert len(calls) == expected_batches         # ceil(20/8)=3 batched calls, NOT 20 per-ticker calls
    assert all(len(c) <= bs for c in calls)       # no batch exceeds batch_size
    assert len(summary["fresh"]) == 20 and not summary["failed"]


def test_already_fresh_tickers_are_not_refetched(monkeypatch, tmp_path):
    db = str(tmp_path / "d.db")
    storage.init_db(db)
    _seed(db, ["A", "B"], datetime.now(timezone.utc).date().isoformat())   # cached to today

    calls = []
    monkeypatch.setattr(data, "_download_with_retry",
                        lambda *a, **k: (calls.append(1), None)[1])
    data.fetch_price_history(["A", "B"], db_path=db)
    assert calls == []                            # nothing to fetch -> zero network calls


# ---------------------------------------------------------------------------
# Rolling fundamentals refresh — flat ~1/refresh_days slice instead of a 5-day cliff
# ---------------------------------------------------------------------------

def test_rolling_fundamentals_covers_all_within_cadence_and_stays_flat(monkeypatch, tmp_path):
    db = str(tmp_path / "f.db"); storage.init_db(db)
    K, RD = 20, 5
    tickers = [f"T{i}" for i in range(K)]
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)
    n = math.ceil(K / RD)                                  # ~1/5 of the universe per run

    seen, per_run = set(), []
    for _ in range(RD):
        fetched = []
        monkeypatch.setattr(data.yf, "Ticker", _fake_yf(fetched))
        data.fetch_fundamentals(tickers, db_path=db, refresh_days=RD)
        per_run.append(len(fetched)); seen |= set(fetched)

    assert seen == set(tickers)                           # every ticker refreshed within RD runs
    assert per_run == [n] * RD                            # flat: exactly the quota each run, no spike


def test_rolling_fundamentals_drains_backlog_flat_no_guard(monkeypatch, tmp_path):
    # A synchronized over-tolerance cache must NOT all refetch at once (no hard guard) — only the n
    # oldest per run, draining the backlog over ceil(backlog/n) runs while staying flat. This is the
    # decision that keeps a synchronized cache from re-spiking every 5 days.
    db = str(tmp_path / "f.db"); storage.init_db(db)
    RD = 5
    tickers = [f"T{i}" for i in range(20)]
    for t in tickers:
        _seed_fund(db, t, age_days=8)                     # ALL over tolerance (synchronized backlog)
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)
    n = math.ceil(20 / RD)

    seen, per_run = set(), []
    for _ in range(RD):
        fetched = []
        monkeypatch.setattr(data.yf, "Ticker", _fake_yf(fetched))
        data.fetch_fundamentals(tickers, db_path=db, refresh_days=RD)
        per_run.append(len(fetched)); seen |= set(fetched)

    assert per_run == [n] * RD                            # flat n/run, NOT all 20 at once (no guard)
    assert seen == set(tickers)                           # backlog fully drained within RD runs


def test_rolling_fundamentals_targets_oldest_and_reuses_young(monkeypatch, tmp_path):
    db = str(tmp_path / "f.db"); storage.init_db(db)
    RD = 5
    tickers = [f"T{i}" for i in range(20)]
    for i, t in enumerate(tickers):
        _seed_fund(db, t, age_days=6 if i < 4 else 0.1)   # 4 over-tolerance, 16 fresh
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)

    fetched = []
    monkeypatch.setattr(data.yf, "Ticker", _fake_yf(fetched))
    data.fetch_fundamentals(tickers, db_path=db, refresh_days=RD)

    assert set(fetched) == {"T0", "T1", "T2", "T3"}       # only the oldest/over-tolerance are refetched
    assert len(fetched) == math.ceil(20 / RD)             # ...and it's the flat quota


def test_rolling_fundamentals_logs_oldest_age(monkeypatch, tmp_path, capsys):
    db = str(tmp_path / "f.db"); storage.init_db(db)
    tickers = ["A", "B", "C"]
    for t, a in (("A", 0.5), ("B", 0.4), ("C", 0.3)):     # all young; A oldest -> refreshed, B becomes oldest
        _seed_fund(db, t, a)
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)
    monkeypatch.setattr(data.yf, "Ticker", _fake_yf([]))

    data.fetch_fundamentals(tickers, db_path=db, refresh_days=5)
    out = capsys.readouterr().out
    m = re.search(r"oldest age now ([\d.]+)d", out)
    assert m and "tolerance 5d" in out                    # the drift line is printed with a numeric age
    assert 0.0 <= float(m.group(1)) <= 0.5                # reflects reality (<= the max seeded age)


def test_rolling_fundamentals_failsoft_keeps_cache_and_retries(monkeypatch, tmp_path):
    db = str(tmp_path / "f.db"); storage.init_db(db)
    storage.upsert_fundamentals("X", {f: 7.0 for f in FUNDAMENTAL_FIELDS},
                                (datetime.now(timezone.utc) - timedelta(days=9)).isoformat(), db_path=db)
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)

    f1 = []
    monkeypatch.setattr(data.yf, "Ticker", _fake_yf(f1, raise_for={"X"}))
    r1 = data.fetch_fundamentals(["X"], db_path=db, refresh_days=5)
    assert "X" in f1                                       # attempted
    assert r1["X"]["trailing_pe"] == 7.0                  # prior cached values kept, not blanked

    f2 = []
    monkeypatch.setattr(data.yf, "Ticker", _fake_yf(f2))
    data.fetch_fundamentals(["X"], db_path=db, refresh_days=5)
    assert "X" in f2                                       # timestamp not advanced -> retried next run


def test_reused_ticker_keeps_values_and_never_cached_is_none(monkeypatch, tmp_path):
    db = str(tmp_path / "f.db"); storage.init_db(db)
    _seed_fund(db, "Y", age_days=0.1)                      # cached & young -> reused, values intact
    monkeypatch.setitem(PARAMS, "fundamentals_fetch_delay_sec", 0)
    fetched = []
    monkeypatch.setattr(data.yf, "Ticker", _fake_yf(fetched))

    universe = ["Y", "Z"] + [f"O{i}" for i in range(8)]   # Z + O* never cached (older than Y)
    res = data.fetch_fundamentals(universe, db_path=db, refresh_days=5)

    assert "Y" not in fetched                              # young + not oldest -> reused (flags stay present)
    assert res["Y"]["trailing_pe"] == 3.0
    unfetched_nocache = [t for t in universe if t != "Y" and t not in fetched]
    assert unfetched_nocache                              # some no-cache names rolled to a later night
    assert all(res[t][f] is None for t in unfetched_nocache for f in FUNDAMENTAL_FIELDS)
