"""Run-health sentinel (#9): the last_success meta round-trips, and `app --status` reports OK when the
log is current and STALE when a newer trading session exists — a trustworthy signal that doesn't depend
on Task Scheduler's flaky Last Result."""
import json
import os
import sys
import tempfile

# app.py lives at the repo root, not under src/ — make it importable regardless of pytest's cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from src import storage


def _db():
    return os.path.join(tempfile.mkdtemp(), "health.db")


def _spy(d):
    return {"ticker": "SPY", "date": d, "open": 1, "high": 1, "low": 1,
            "close": 1, "volume": 1, "timestamp_fetched": "t"}


def test_meta_roundtrips():
    db = _db(); storage.init_db(db)
    assert storage.get_meta("last_success", db_path=db) is None
    storage.set_meta("last_success", "{}", db_path=db)
    assert storage.get_meta("last_success", db_path=db) == "{}"


def test_status_with_no_prior_success(capsys):
    db = _db(); storage.init_db(db)
    app._print_status(db)
    assert "no successful run recorded" in capsys.readouterr().out


def test_record_run_success_then_status_ok_then_stale(capsys):
    db = _db(); storage.init_db(db)
    storage.upsert_price_rows([_spy("2026-07-20")], db_path=db)     # latest session so far
    app._record_run_success({"run_date": "2026-07-20", "tickers_scored": 5}, [], db)

    rec = json.loads(storage.get_meta("last_success", db_path=db))
    assert rec["run_date"] == "2026-07-20" and rec["tickers_scored"] == 5

    app._print_status(db)
    assert "OK" in capsys.readouterr().out                          # last run == latest session

    storage.upsert_price_rows([_spy("2026-07-21")], db_path=db)     # a newer session appears, not yet run
    app._print_status(db)
    assert "STALE" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Phase 0 scale prerequisites
# ---------------------------------------------------------------------------

def test_earnings_dates_are_cached_and_refreshed_on_a_rolling_slice(tmp_path, monkeypatch):
    """Earnings dates used to be fetched per ticker PER RUN with no cache and no throttle: 519 raw
    HTTP requests a night against Yahoo's ~360/hr soft limit, and the most likely single route to an
    IP block. A block stops data collection entirely, which is the one failure this project cannot
    absorb. Only the oldest ~1/refresh_days slice may hit the network on any given run."""
    from src import data, storage
    db = str(tmp_path / "e.db")
    storage.init_db(db)
    calls = []

    def fake_fetch(ticker):
        calls.append(ticker)
        return "2026-09-15", False

    monkeypatch.setattr(data, "fetch_next_earnings_date", fake_fetch)
    monkeypatch.setattr(data.time, "sleep", lambda *_a: None)
    tickers = [f"T{i}" for i in range(20)]

    data.fetch_earnings_dates(tickers, db_path=db, refresh_days=5)
    assert len(calls) == 4, f"expected ceil(20/5)=4 network calls, got {len(calls)}"

    # second run: the 4 just-fetched are freshest, so a DIFFERENT 4 are refreshed
    first_round = set(calls)
    calls.clear()
    data.fetch_earnings_dates(tickers, db_path=db, refresh_days=5)
    assert len(calls) == 4
    assert not (set(calls) & first_round), "refreshed the same tickers twice - not rotating"


def test_earnings_cache_distinguishes_no_date_published_from_never_asked(tmp_path, monkeypatch):
    # A stored NULL with fetch_failed=1 means "we asked, there is no date". No row at all means
    # "never asked". Collapsing the two would make a missing date look like a fetched fact.
    from src import data, storage
    db = str(tmp_path / "e.db")
    storage.init_db(db)
    monkeypatch.setattr(data, "fetch_next_earnings_date", lambda t: (None, True))
    monkeypatch.setattr(data.time, "sleep", lambda *_a: None)

    assert storage.get_cached_earnings_date("AAA", db_path=db) is None      # never asked
    out = data.fetch_earnings_dates(["AAA"], db_path=db, refresh_days=1)
    row = storage.get_cached_earnings_date("AAA", db_path=db)
    assert row is not None and row["earnings_date"] is None and row["fetch_failed"] == 1
    assert out["AAA"] == (None, True)


def test_days_until_accepts_an_iso_string_from_the_cache():
    """The cache stores dates as TEXT. If _days_until only accepted date objects it would return None
    for every ticker, silently disabling the earnings penalty across the whole universe while looking
    like nothing had changed."""
    import app
    from datetime import date, timedelta
    target = date.today() + timedelta(days=3)
    assert app._days_until(target.isoformat()) == 3
    assert app._days_until(target) == 3
    assert app._days_until("not-a-date") is None
    assert app._days_until(None) is None


def test_export_writes_only_the_active_version_by_default(tmp_path):
    """score_history.csv was every row of every model_version, rewritten nightly: 733 MB already, and
    past 3 GB after a v0.5 backfill. Frozen versions can never change, so rewriting them nightly is
    pure cost. The full dump stays available on demand."""
    import app
    from src import storage
    from src.config import PARAMS
    db = str(tmp_path / "s.db")
    storage.init_db(db)
    rows = []
    for v in (PARAMS["model_version"], "v0.1_price_volume_only"):
        for i in range(3):
            rows.append({"run_date": "2025-01-02", "ticker": f"T{i}", "benchmark": "SPY",
                         "model_version": v, "timestamp_fetched": "t", "backfilled": 1,
                         "earnings_risk_unknown": 1, "score_20d": 50.0 + i})
    storage.upsert_feature_snapshots(rows, db_path=db)

    out = str(tmp_path / "out")
    import os
    os.makedirs(out, exist_ok=True)
    app._export_csvs(db, out)
    import pandas as pd
    hist = pd.read_csv(os.path.join(out, "score_history.csv"))
    assert set(hist["model_version"]) == {PARAMS["model_version"]}       # active only

    app._export_csvs(db, out, full_history=True)
    hist_full = pd.read_csv(os.path.join(out, "score_history.csv"))
    assert set(hist_full["model_version"]) == {PARAMS["model_version"], "v0.1_price_volume_only"}


def test_frozen_versions_are_skipped_but_their_report_rows_are_carried_forward(tmp_path):
    """A frozen version's snapshots are immutable, so re-deriving its forward returns nightly can only
    reproduce the same numbers. Skipping it must NOT drop it from the report - a version vanishing
    reads as 'it stopped performing' rather than 'it stopped being recomputed'."""
    import os
    import pandas as pd
    from src import evaluation, storage
    from src.config import FROZEN_MODEL_VERSIONS, PARAMS
    frozen = sorted(FROZEN_MODEL_VERSIONS)[0]
    db = str(tmp_path / "f.db")
    storage.init_db(db)
    out = str(tmp_path / "o")
    os.makedirs(out, exist_ok=True)

    # a pre-existing report already containing the frozen version's rows
    pd.DataFrame([{"report_type": "bucket", "model_version": frozen, "horizon": "20d",
                   "label": "strong", "n": 42, "avg_future_excess_return": 0.01}]).to_csv(
        os.path.join(out, "performance_review.csv"), index=False)

    storage.upsert_feature_snapshots([
        {"run_date": "2025-01-02", "ticker": "T1", "benchmark": "SPY", "model_version": frozen,
         "timestamp_fetched": "t", "backfilled": 1, "earnings_risk_unknown": 1, "score_20d": 50.0}],
        db_path=db)

    review = evaluation.run_evaluation(db_path=db, output_dir=out)
    # the frozen version was not recomputed, but its prior rows survive
    assert frozen in set(review["model_version"]), "frozen version dropped from the report entirely"
