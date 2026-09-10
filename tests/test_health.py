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

    # `today` is passed explicitly rather than defaulting to the real clock. A status test that
    # reads date.today() passes on the day it is written and drifts into failure later — and the
    # wall-clock check added after the 2026-09-09 missed run makes that drift immediate.
    app._print_status(db, today="2026-07-21")                       # the very next day
    assert "OK" in capsys.readouterr().out                          # last run == latest session

    storage.upsert_price_rows([_spy("2026-07-21")], db_path=db)     # a newer session appears, not yet run
    app._print_status(db, today="2026-07-22")
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


# ---------------------------------------------------------------------------
# The circular-staleness bug (found live on 2026-09-09)
# ---------------------------------------------------------------------------

def test_weekdays_between_ignores_weekends():
    assert app.weekdays_between("2026-09-08", "2026-09-10") == 1      # Tue -> Thu, Wed missed
    assert app.weekdays_between("2026-09-08", "2026-09-09") == 0      # consecutive sessions
    assert app.weekdays_between("2026-09-04", "2026-09-07") == 0      # Fri -> Mon, weekend only
    assert app.weekdays_between("2026-09-04", "2026-09-08") == 1      # Fri -> Tue, Mon missed


def test_status_detects_a_missed_run_that_the_cached_check_calls_ok(capsys):
    """THE regression test. Reproduces 2026-09-09 exactly.

    The nightly run was killed two minutes in, so no new price bar was ever fetched. The original
    check compared the last good run_date against MAX(date) in price_history — but with no fetch,
    that maximum is still the PREVIOUS session, which equals the last good run_date, so it reported
    OK. The check was measuring staleness against its own stale cache and structurally could not
    see a missed run.

    A whole session vanished from the live record while the health command said everything was
    fine. That is the exact failure shape this project exists to catch."""
    db = _db()
    storage.init_db(db)
    storage.upsert_price_rows([_spy("2026-09-08")], db_path=db)
    storage.set_meta("last_success", json.dumps({
        "run_date": "2026-09-08", "model_version": "v0.5_expanded_universe",
        "finished_at": "2026-09-09T01:15:53+00:00", "tickers_scored": 1521,
        "recovered_days": []}), db_path=db)

    # Wednesday the 9th was a trading session. It is now Thursday the 10th.
    app._print_status(db, today="2026-09-10")
    out = capsys.readouterr().out
    assert "SUSPECT" in out, "a missed weekday session was reported as OK"
    assert "did not complete" in out


def test_status_still_says_ok_over_a_normal_weekend(capsys):
    """The counterweight: Friday's run, checked on Saturday or Monday morning, is genuinely fine.
    A staleness check that cried wolf every weekend would be turned off within a week."""
    db = _db()
    storage.init_db(db)
    storage.upsert_price_rows([_spy("2026-09-04")], db_path=db)   # Friday
    storage.set_meta("last_success", json.dumps({
        "run_date": "2026-09-04", "model_version": "v", "finished_at": "x",
        "tickers_scored": 1, "recovered_days": []}), db_path=db)
    app._print_status(db, today="2026-09-07")                     # Monday
    assert "OK" in capsys.readouterr().out


def test_status_still_reports_plain_stale_when_new_prices_did_arrive(capsys):
    """The original check is kept, not replaced: when a fetch DID happen but scoring did not, the
    cached comparison is the more precise signal and should still fire."""
    db = _db()
    storage.init_db(db)
    storage.upsert_price_rows([_spy("2026-09-08"), _spy("2026-09-09")], db_path=db)
    storage.set_meta("last_success", json.dumps({
        "run_date": "2026-09-08", "model_version": "v", "finished_at": "x",
        "tickers_scored": 1, "recovered_days": []}), db_path=db)
    app._print_status(db, today="2026-09-10")
    out = capsys.readouterr().out
    assert "STALE" in out and "2026-09-09" in out


# ---------------------------------------------------------------------------
# Partial-day coverage (found live on 2026-09-10)
# ---------------------------------------------------------------------------

def test_a_partially_scored_day_is_detected():
    """Recovery only finds sessions with ZERO snapshots. A session that scored 945 of 1,521 names
    is "present" by that test and never revisited — yet its sector-neutral percentile ranks were
    computed on 62% of the universe. That is a silently WRONG ranking, not a missing one, which is
    strictly worse. Observed live on 2026-09-10."""
    counts = [(f"2026-08-{d:02d}", 1521) for d in range(1, 11)]
    counts.append(("2026-09-10", 945))
    thin = app.thin_live_days(counts)
    assert len(thin) == 1
    run_date, n, expected = thin[0]
    assert run_date == "2026-09-10" and n == 945 and expected == 1521


def test_normal_variation_is_not_flagged():
    """A handful of names failing a fetch is routine. A check that fires on every ordinary run gets
    ignored, which is the same as not having it."""
    counts = [(f"2026-08-{d:02d}", 1521) for d in range(1, 11)]
    counts.append(("2026-09-10", 1495))       # ~26 names short, ~98%
    assert app.thin_live_days(counts) == []


def test_the_norm_is_a_median_so_one_thin_day_cannot_lower_the_bar():
    """With a mean, a single 62% day would drag the expectation down and help the NEXT thin day
    pass — the check would quietly erode exactly when it is needed most."""
    counts = [(f"2026-08-{d:02d}", 1500) for d in range(1, 11)]
    counts.append(("2026-09-09", 400))        # a very thin day
    counts.append(("2026-09-10", 1100))       # would pass against a dragged-down mean
    flagged = {d for d, _, _ in app.thin_live_days(counts)}
    assert flagged == {"2026-09-09", "2026-09-10"}


def test_days_without_enough_history_are_left_alone():
    """The first few live days have nothing to be abnormal relative to. Guessing there would flag
    the start of every new model version."""
    assert app.thin_live_days([("2026-08-01", 10), ("2026-08-02", 1500)]) == []
