"""Journal + AI-brief proof tests (spec's "Tests" section):
- journal entry completeness on a synthetic run;
- idempotency (same run_date twice -> exactly one entry, replaced not duplicated);
- brief skip path when no API key is set;
- brief failure path leaves the journal entry intact.
Plus: top-10 movement (entered/exited/movers) and DAILY_LOG.md regeneration from the table.
"""

import json
import os
import tempfile

import pandas as pd
import pytest

from src import brief, journal, storage
from src.config import PARAMS


def _temp_db():
    return os.path.join(tempfile.mkdtemp(), "journal_test.db")


def _seed_two_live_runs(db):
    """Two live run_dates for one ticker set, so movement/movers have something to compare."""
    storage.init_db(db)
    ts = "2026-07-01T00:00:00Z"
    prev = {"GL": 80.0, "ALL": 88.0, "AAPL": 55.0, "MSFT": 40.0, "NVDA": 70.0}
    today = {"GL": 87.2, "ALL": 86.8, "CINF": 84.7, "AAPL": 52.1, "MSFT": 34.5}
    for run_date, scores in (("2026-07-01", prev), ("2026-07-04", today)):
        for tkr, s in scores.items():
            # Seed whichever column the log currently DISPLAYS, so this fixture keeps testing the
            # real path if the display horizon moves again (it moved 20d -> 120d once the decile
            # spreads showed 20d carries no signal).
            storage.upsert_feature_snapshot({
                "run_date": run_date, "ticker": tkr, "benchmark": "SPY",
                "model_version": "v0.2_fundamentals_added", "backfilled": 0,
                "earnings_risk_unknown": 1, journal.display_score_column(): s,
                "timestamp_fetched": ts,
            }, db_path=db)
    return db


def _run_context(run_date="2026-07-04", backfilled=False):
    return {
        "run_date": run_date, "model_version": "v0.2_fundamentals_added",
        "backfilled": backfilled, "runtime_sec": 42.3, "tickers_scored": 5,
        "fetch_summary": {"fresh": ["GL", "ALL"], "cached_only": [], "failed": ["ZZZ"]},
        "fundamentals_summary": "fetched 5, failed 0",
        "warnings": ["1 ticker skipped (stale)"],
    }


# ---------------------------------------------------------------------------
# Completeness + movement
# ---------------------------------------------------------------------------

def test_journal_entry_is_complete_on_a_synthetic_run():
    db = _seed_two_live_runs(_temp_db())
    out_dir = tempfile.mkdtemp()
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=out_dir)

    # every top-level section present (journal_v2 four-section layout)
    assert entry["schema"] == "journal_v2"
    for section in ("run", "todays_rankings", "matured_cohorts", "running_scoreboard",
                    "live_validation"):
        assert section in entry
    # run metadata carries the run's own facts (which live in no CSV)
    assert entry["run"]["mode"] == "live"
    assert entry["run"]["tickers_scored"] == 5
    assert entry["run"]["fetch"]["failed"] == ["ZZZ"]
    assert entry["run"]["warnings"] == ["1 ticker skipped (stale)"]
    # DAILY_LOG.md was written and mirrors the entry
    log = open(os.path.join(out_dir, "DAILY_LOG.md"), encoding="utf-8").read()
    assert "2026-07-04" in log and "Today's Rankings" in log and "Live validation tracker" in log


def test_rankings_movement_entered_exited_and_movers():
    db = _seed_two_live_runs(_temp_db())
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=tempfile.mkdtemp())
    mv = entry["todays_rankings"]

    assert mv["top_10"][0]["ticker"] == "GL"                        # 87.2 is highest today
    assert mv["compared_to_prev_live_run"] == "2026-07-01"
    assert "CINF" in mv["entered_top_10"]                           # new name today
    assert "NVDA" in mv["exited_top_10"]                            # dropped out of the pool
    # GL rose +7.2, MSFT fell -5.5 — joined on ticker, not row position
    assert any(g["ticker"] == "GL" and g["delta"] == pytest.approx(7.2) for g in mv["biggest_gainers"])
    assert any(l["ticker"] == "MSFT" and l["delta"] == pytest.approx(-5.5) for l in mv["biggest_losers"])


def test_v02_validation_tracks_live_day_count_and_pending_ic():
    db = _seed_two_live_runs(_temp_db())
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=tempfile.mkdtemp())
    v = entry["live_validation"]
    assert v["live_trading_days_accumulated"] == 2                  # two distinct live run_dates
    assert v["latest_live_run_date"] == "2026-07-04"
    # no performance_review.csv in this temp dir -> factor IC pending (None), not invented
    assert all(v["new_factor_ic"][c] is None for c in
               ("value_component", "quality_component", "short_interest_component"))


def test_first_live_run_has_no_prior_comparison():
    db = _temp_db()
    storage.init_db(db)
    for tkr, s in {"GL": 80.0, "ALL": 70.0}.items():
        storage.upsert_feature_snapshot({
            "run_date": "2026-07-04", "ticker": tkr, "benchmark": "SPY",
            "model_version": "v0.2_fundamentals_added", "backfilled": 0,
            "earnings_risk_unknown": 1, journal.display_score_column(): s,
            "timestamp_fetched": "2026-07-04T00:00:00Z",
        }, db_path=db)
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=tempfile.mkdtemp())
    mv = entry["todays_rankings"]
    assert mv["compared_to_prev_live_run"] is None
    assert mv["entered_top_10"] == [] and mv["exited_top_10"] == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_journal_is_idempotent_same_date_twice_one_entry():
    db = _seed_two_live_runs(_temp_db())
    out_dir = tempfile.mkdtemp()
    journal.run_journal(_run_context(), db_path=db, output_dir=out_dir)
    journal.run_journal(_run_context(), db_path=db, output_dir=out_dir)  # re-run same date

    rows = storage.load_all_journal_entries(db)
    same_date = [r for r in rows if r["run_date"] == "2026-07-04"]
    assert len(same_date) == 1                                     # replaced, not duplicated
    # DAILY_LOG.md has exactly one heading for that date
    log = open(os.path.join(out_dir, "DAILY_LOG.md"), encoding="utf-8").read()
    assert log.count("## 2026-07-04") == 1


# ---------------------------------------------------------------------------
# Brief — graceful degradation
# ---------------------------------------------------------------------------

def test_brief_skips_cleanly_with_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    entry = {"schema": "journal_v1", "run": {"run_date": "2026-07-04"}}
    text, note = brief.generate_brief(entry)
    assert text is None
    assert note == "brief skipped — no API key"


def test_brief_skips_when_empty_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")  # whitespace-only counts as absent
    text, note = brief.generate_brief({"run": {}})
    assert text is None and note == "brief skipped — no API key"


def test_brief_failure_leaves_journal_intact(monkeypatch):
    # Journal is written first; then a brief API error must not touch or remove the entry.
    db = _seed_two_live_runs(_temp_db())
    out_dir = tempfile.mkdtemp()
    ctx = _run_context()
    entry = journal.run_journal(ctx, db_path=db, output_dir=out_dir)

    # Force generate_brief down the API-error path (key present, but the client raises).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    class _BoomClient:
        def __init__(self, *a, **k):
            raise RuntimeError("simulated API/network failure")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _BoomClient)

    result = brief.run_brief(entry, ctx, db_path=db, output_dir=out_dir)
    assert result is None                                          # brief failed, returned None

    # the journal entry still exists, unchanged, with no brief attached
    row = storage.get_journal_entry("2026-07-04", "v0.2_fundamentals_added", db_path=db)
    assert row is not None and row["brief"] is None
    assert json.loads(row["entry_json"])["schema"] == "journal_v2"
    # DAILY_LOG.md still has the entry
    log = open(os.path.join(out_dir, "DAILY_LOG.md"), encoding="utf-8").read()
    assert "## 2026-07-04" in log


def test_brief_success_path_attaches_and_rerenders(monkeypatch):
    db = _seed_two_live_runs(_temp_db())
    out_dir = tempfile.mkdtemp()
    ctx = _run_context()
    entry = journal.run_journal(ctx, db_path=db, output_dir=out_dir)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    class _Block:
        type = "text"
        text = "Live run scored 5 tickers; nothing failed of note."

    class _Resp:
        content = [_Block()]

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = self

        def create(self, **k):
            assert k["model"] == "claude-sonnet-4-6"       # spec-mandated model
            return _Resp()

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)

    result = brief.run_brief(entry, ctx, db_path=db, output_dir=out_dir)
    assert result and "scored 5 tickers" in result
    row = storage.get_journal_entry("2026-07-04", "v0.2_fundamentals_added", db_path=db)
    assert row["brief"] == result
    log = open(os.path.join(out_dir, "DAILY_LOG.md"), encoding="utf-8").read()
    assert "**Brief:**" in log and "scored 5 tickers" in log


# ---------------------------------------------------------------------------
# Section 2 — matured-cohort grading (trading-day maturity + grade-once)
# ---------------------------------------------------------------------------

# A calendar with a weekend gap: 06-06 and 06-07 are NOT trading days. Five TRADING sessions
# after 2026-06-01 is 2026-06-08 — but only three CALENDAR days would land on 06-04 and five on
# 06-06. So a correct trading-day counter must pick 06-01 as the cohort maturing on 06-08.
_CAL = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05",
        "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]


def _syn_calendar(n_sessions, start="2026-01-01"):
    """n consecutive WEEKDAY sessions (skips Sat/Sun) — a synthetic NYSE-ish calendar long enough to
    exercise 20/60/120-day maturities without hand-writing dates."""
    import datetime as _dt
    d, out = _dt.date.fromisoformat(start), []
    while len(out) < n_sessions:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += _dt.timedelta(days=1)
    return out


def _cohort_rows(horizon=5, run_date="2026-06-01", backfilled=0, version="v0.3_sector_neutral"):
    # Two strong (one hit, one miss) + two weak (one hit, one miss), so each bucket hit rate is 50%.
    hk, ek = f"score_{horizon}d", f"future_excess_return_{horizon}d"
    return [
        {"run_date": run_date, "backfilled": backfilled, "model_version": version, "ticker": "A", hk: 90, ek: 0.02},
        {"run_date": run_date, "backfilled": backfilled, "model_version": version, "ticker": "B", hk: 85, ek: -0.01},
        {"run_date": run_date, "backfilled": backfilled, "model_version": version, "ticker": "C", hk: 10, ek: -0.02},
        {"run_date": run_date, "backfilled": backfilled, "model_version": version, "ticker": "D", hk: 20, ek: 0.03},
    ]


def test_cohort_matures_on_trading_day_not_calendar_day():
    cohorts = journal._grade_all_cohorts(_cohort_rows(), _CAL)
    sec = journal._matured_cohorts_section(cohorts, "2026-06-08")
    assert len(sec["cohorts"]) == 1
    c = sec["cohorts"][0]
    assert c["snapshot_date"] == "2026-06-01"          # 5 trading sessions back, not 5 calendar days
    assert c["horizon"] == "5d"
    assert c["n"] == 4
    assert c["strong_n"] == 2 and c["weak_n"] == 2     # A/B strong, C/D weak
    # per-bucket gating (#1): each bucket has n=2 < scoreboard_min_bucket_n, so the hit rate is
    # suppressed (None -> "n/a") rather than reported as a meaningless "50% of 2".
    assert c["strong_hit_pct"] is None and c["weak_hit_pct"] is None
    assert c["low_confidence"] is (4 < PARAMS["cohort_low_confidence_min_n"])


def test_cohort_is_graded_exactly_once():
    # The 2026-06-01 5d cohort matures on 06-08; the NEXT day (06-09) must not re-grade it.
    cohorts = journal._grade_all_cohorts(_cohort_rows(), _CAL)
    assert len(journal._matured_cohorts_section(cohorts, "2026-06-08")["cohorts"]) == 1
    assert journal._matured_cohorts_section(cohorts, "2026-06-09")["cohorts"] == []


def test_cohort_backfill_excluded_from_section2_live_slice():
    # A backfill cohort (backfilled=1) is not a live prediction — Section 2 (live-only) skips it,
    # though Section 3 still counts it in the backfill column.
    cohorts = journal._grade_all_cohorts(_cohort_rows(backfilled=1), _CAL)
    assert journal._matured_cohorts_section(cohorts, "2026-06-08")["cohorts"] == []


def test_cohort_grades_across_versions_and_labels_by_version():
    # A cohort from an EARLIER model version must still be graded and labelled by its version —
    # grading must not reset on a version bump (the v0.2-era-snapshots bug).
    rows = _cohort_rows(version="v0.2_fundamentals_added")
    cohorts = journal._grade_all_cohorts(rows, _CAL)
    sec = journal._matured_cohorts_section(cohorts, "2026-06-08")
    assert len(sec["cohorts"]) == 1
    assert sec["cohorts"][0]["model_version"] == "v0.2_fundamentals_added"
    md = "\n".join(journal._render_section2(sec))
    assert "v0.2_fundamentals_added" in md and "2026-06-01" in md


def test_longer_horizons_mature_correctly_not_just_5d():
    # 20/60/120-day cohorts must trigger on their exact trading-day maturity, not only the 5d path.
    cal = _syn_calendar(200)
    for n in (20, 60, 120):
        cohorts = journal._grade_all_cohorts(_cohort_rows(horizon=n, run_date=cal[0]), cal)
        assert len(journal._matured_cohorts_section(cohorts, cal[n])["cohorts"]) == 1   # matures on cal[n]
        assert journal._matured_cohorts_section(cohorts, cal[n - 1])["cohorts"] == []
        assert journal._matured_cohorts_section(cohorts, cal[n + 1])["cohorts"] == []


def test_section3_equals_sum_of_section2_over_all_days():
    # THE invariant: Section 3's cumulative live n == the sum of every day's Section 2 live cohort n,
    # per bucket — the two are the same numbers viewed two ways and cannot drift.
    cal = _syn_calendar(30)
    rows = _cohort_rows(horizon=5, run_date=cal[0]) + _cohort_rows(horizon=5, run_date=cal[1])
    cohorts = journal._grade_all_cohorts(rows, cal)

    sb = journal._running_scoreboard_section(cohorts, rows, cal[-1])   # cumulative as of latest day
    s3 = (sb["live"]["5d"]["strong"]["n"], sb["live"]["5d"]["weak"]["n"])

    s2_strong = s2_weak = 0
    for d in cal:
        for c in journal._matured_cohorts_section(cohorts, d)["cohorts"]:
            s2_strong += c["strong_n"]
            s2_weak += c["weak_n"]
    assert (s2_strong, s2_weak) == s3
    assert s3 == (4, 4)                                  # 2 strong + 2 weak per cohort × 2 cohorts


# ---------------------------------------------------------------------------
# Section 3 — running scoreboard (live vs backfill split + min-n gating)
# ---------------------------------------------------------------------------

def test_section1_excludes_etfs_from_top10_but_keeps_them_in_movers():
    # Benchmark ETFs (sector == "Index") are dropped from the top-10 DISPLAY only; a big ETF move
    # still shows in the movers line (full universe).
    today_rows = [{"ticker": "XLF", "score_20d": 99.0}, {"ticker": "ALL", "score_20d": 88.0},
                  {"ticker": "GL", "score_20d": 80.0}]
    today_scores = {"XLF": 99.0, "ALL": 88.0, "GL": 80.0}
    prev_scores = {"XLF": 50.0, "ALL": 85.0, "GL": 82.0}
    sector_map = {"XLF": "Index", "ALL": "Financials", "GL": "Financials"}
    sec = journal._todays_rankings_section(today_rows, today_scores, prev_scores, "2026-07-07", sector_map)

    tickers = [r["ticker"] for r in sec["top_10"]]
    assert "XLF" not in tickers and tickers[0] == "ALL"          # ETF filtered; highest non-ETF leads
    assert any(g["ticker"] == "XLF" for g in sec["biggest_gainers"])  # +49 still visible in movers


def test_running_scoreboard_splits_live_backfill_and_gates_small_buckets():
    min_n = PARAMS["scoreboard_min_bucket_n"]
    cal = _syn_calendar(60)
    live_d, bf_d = cal[0], cal[1]
    rows = []
    for i in range(25):  # live strong: 15 hits / 25 -> 60%
        rows.append({"backfilled": 0, "run_date": live_d, "ticker": f"S{i}",
                     "score_20d": 90, "future_excess_return_20d": 0.01 if i < 15 else -0.01})
    for i in range(5):   # live weak: only 5 -> below min_n -> None
        rows.append({"backfilled": 0, "run_date": live_d, "ticker": f"W{i}",
                     "score_20d": 10, "future_excess_return_20d": -0.01})
    for i in range(22):  # backfill strong: 11 hits / 22 -> 50%
        rows.append({"backfilled": 1, "run_date": bf_d, "ticker": f"BS{i}",
                     "score_20d": 95, "future_excess_return_20d": 0.01 if i < 11 else -0.02})

    cohorts = journal._grade_all_cohorts(rows, cal)
    sb = journal._running_scoreboard_section(cohorts, rows, cal[-1])   # cumulative as of latest day
    assert sb["live"]["20d"]["strong"]["hit_pct"] == 60.0
    assert sb["live"]["20d"]["strong"]["n"] == 25
    assert sb["live"]["20d"]["weak"]["hit_pct"] is None      # 5 < min_n, gated to n/a
    assert sb["live"]["20d"]["weak"]["n"] == 5
    assert sb["backfill"]["20d"]["strong"]["hit_pct"] == 50.0
    assert 5 < min_n <= 25                                   # sanity: thresholds make this test meaningful


def test_section2_per_bucket_gating_shows_large_hides_small():
    # #1: a bucket with n >= scoreboard_min_bucket_n shows its hit rate; a small bucket is suppressed to
    # "n/a (n=X)" rather than reported as noise — Section 2 gates buckets exactly like Section 3.
    min_n = PARAMS["scoreboard_min_bucket_n"]
    cal = _syn_calendar(20)
    rows = []
    for i in range(min_n):    # strong: exactly min_n names, even i = hit -> a real rate is shown
        rows.append({"backfilled": 0, "run_date": cal[0], "ticker": f"S{i}",
                     "score_5d": 90, "future_excess_return_5d": 0.01 if i % 2 == 0 else -0.01})
    for i in range(3):        # weak: 3 names -> below min_n -> gated to None
        rows.append({"backfilled": 0, "run_date": cal[0], "ticker": f"W{i}",
                     "score_5d": 10, "future_excess_return_5d": 0.01})
    cohorts = journal._grade_all_cohorts(rows, cal)
    c = journal._matured_cohorts_section(cohorts, cal[5])["cohorts"][0]
    assert c["strong_n"] == min_n and c["strong_hit_pct"] is not None   # large bucket: rate shown
    assert c["weak_n"] == 3 and c["weak_hit_pct"] is None               # small bucket: gated
    rendered = "\n".join(journal._render_section2({"cohorts": [c]}))
    assert "too few to score" in rendered and ("needs %d" % min_n) in rendered
    assert "only 3 names" in rendered
    assert "n/a" not in rendered, "a suppressed bucket must explain itself"


def test_recovered_rows_excluded_from_section2_and_section3():
    # #2: recovered rows (stale fundamentals in the composite) leave BOTH Section 2 and Section 3 via the
    # one shared filter, so the two can't drift; genuine live rows are untouched.
    cal = _syn_calendar(30)
    live = _cohort_rows(horizon=5, run_date=cal[0])              # matures cal[5]
    recov = _cohort_rows(horizon=5, run_date=cal[1])             # would mature cal[6]
    for r in recov:
        r["recovered"] = 1
    cohorts = journal._grade_all_cohorts(live + recov, cal)
    assert len(journal._matured_cohorts_section(cohorts, cal[5])["cohorts"]) == 1   # live graded
    assert journal._matured_cohorts_section(cohorts, cal[6])["cohorts"] == []       # recovered dropped
    sb = journal._running_scoreboard_section(cohorts, live + recov, cal[-1])
    assert sb["live"]["5d"]["strong"]["n"] == 2 and sb["live"]["5d"]["weak"]["n"] == 2  # only the 4 live


def test_run_journal_uses_injected_evaluated_rows_and_skips_recompute(monkeypatch):
    # #4: when app injects evaluated_rows, run_journal must NOT recompute the forward-return join.
    db = _seed_two_live_runs(_temp_db())
    out = tempfile.mkdtemp()

    def _boom(*a, **k):
        raise AssertionError("evaluate_all_snapshots must not be called when rows are injected")

    monkeypatch.setattr(journal.evaluation, "evaluate_all_snapshots", _boom)
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=out, evaluated_rows=[])
    assert entry["schema"] == "journal_v2"


# ---------------------------------------------------------------------------
# Section 4 — live validation tracker (4a / 4b too-early + drift-flag paths)
# ---------------------------------------------------------------------------

def _review(rows):
    return pd.DataFrame(rows)


def _comp_row(component, horizon, n, ic, ic_recent=None, n_recent=0,
              version="v0.2_fundamentals_added"):
    return {"report_type": "component_correlation", "model_version": version, "horizon": horizon,
            "component": component, "n": n, "pearson_ic": ic, "spearman_ic": ic,
            "spearman_ic_recent": ic_recent, "n_recent": n_recent}


def test_4a_too_early_and_4b_accruing_paths():
    df = _review([
        _comp_row("value_component", "20d", n=3, ic=0.20),        # 4a: n<threshold -> too early
        _comp_row("quality_component", "20d", n=50, ic=0.08),     # 4a: enough -> real number
        _comp_row("trend_component", "60d", n=100, ic=0.10),      # 4b: no recent IC -> accruing
    ])
    sec = journal._live_validation_section(df, "v0.2_fundamentals_added", ["2026-07-01"])

    assert sec["new_factor_ic"]["value_component"]["20d"]["too_early"] is True
    assert sec["new_factor_ic"]["value_component"]["20d"]["n"] == 3
    assert sec["new_factor_ic"]["quality_component"]["20d"]["too_early"] is False
    assert sec["new_factor_ic"]["short_interest_component"] is None   # no row -> None, not invented

    trend = next(d for d in sec["drift"] if d["component"] == "trend_component")
    assert trend["too_early"] is True and trend["drift_flag"] is False

    md = "\n".join(journal._render_section4(sec))
    assert "too early (n=3)" in md            # 4a
    assert "too early — accruing" in md       # 4b


def test_4b_flags_material_drift_once_recent_window_populated():
    df = _review([
        _comp_row("trend_component", "120d", n=100, ic=0.11, ic_recent=0.02, n_recent=80),
    ])
    sec = journal._live_validation_section(df, "v0.2_fundamentals_added", ["2026-07-01"])
    trend = sec["drift"][0]
    assert trend["too_early"] is False
    assert trend["drift_flag"] is True        # |0.02 - 0.11| = 0.09 >= threshold
    assert "DRIFT" in "\n".join(journal._render_section4(sec))


def test_journal_sources_its_own_sector_map_when_none_is_supplied(tmp_path):
    """An empty sector_map degrades silently and badly.

    Sectors render as "-" (cosmetic), but the benchmark-ETF exclusion is computed FROM this same map,
    so an empty one puts XLV/XLE/XLB at the top of "Today's Rankings" as research picks. Plausible
    wrong output, which is the exact failure mode this project keeps hitting. The journal therefore
    sources its own map rather than trusting every caller to pass one."""
    import pandas as pd
    from src.config import ETF_SECTOR_LABEL
    wl = tmp_path / "watchlist.csv"
    pd.DataFrame([
        {"ticker": "AAA", "sector": "Financials", "benchmark": "XLF"},
        {"ticker": "XLF", "sector": ETF_SECTOR_LABEL, "benchmark": "SPY"},
    ]).to_csv(wl, index=False)
    m = journal._sector_map_from_watchlist(str(wl))
    assert m == {"AAA": "Financials", "XLF": ETF_SECTOR_LABEL}
    # and the ETF is identifiable from it, which is what drives the top-10 exclusion
    assert [t for t, s in m.items() if s == ETF_SECTOR_LABEL] == ["XLF"]


def test_sector_map_helper_is_fail_soft_on_a_missing_watchlist(tmp_path, capsys):
    # The journal must never break a completed run; a missing watchlist warns and returns {}.
    out = journal._sector_map_from_watchlist(str(tmp_path / "nope.csv"))
    assert out == {}
    assert "could not read watchlist" in capsys.readouterr().out


def test_benchmark_etfs_are_excluded_from_the_top_10():
    """The ETFs are scored and stored like any other row, but they are benchmarks, not candidates.
    Ranking XLV as the #1 research pick is meaningless."""
    from src.config import ETF_SECTOR_LABEL
    sector_map = {"AAA": "Financials", "BBB": "Industrials", "XLV": ETF_SECTOR_LABEL}
    today_rows = [{"ticker": t, "score_20d": s} for t, s in
                  [("XLV", 99.0), ("AAA", 80.0), ("BBB", 70.0)]]
    scores = {"XLV": 99.0, "AAA": 80.0, "BBB": 70.0}
    sec = journal._todays_rankings_section(today_rows, scores, {}, None, sector_map)
    tickers = [r["ticker"] for r in sec["top_10"]]
    assert "XLV" not in tickers, "a benchmark ETF was ranked as a research pick"
    assert tickers[:2] == ["AAA", "BBB"]


def test_regenerated_entry_still_renders_every_section():
    """A re-journaled past date has no runtime or ticker count - those belong to the run that already
    finished. The first attempt at handling that early-returned, which silently dropped all four
    sections from the entry. Both branches must produce a complete entry."""
    base = {"run_date": "D", "model_version": "v", "mode": "live", "fetch": {}}
    full = journal._render_entry_v2({"run": dict(base, tickers_scored=10, runtime_sec=5)})
    regen = journal._render_entry_v2({"run": dict(base)})
    assert full.count("###") == 4, "a completed run lost sections"
    assert regen.count("###") == 4, "a regenerated entry lost sections"
    assert "scored 10 tickers" in full
    assert "regenerated from stored snapshots" in regen
    assert "None tickers" not in regen and "unknown time" not in regen


def test_cohort_line_accounts_for_every_graded_name():
    """The owner read "6 strong vs 287 weak" out of 515 and asked why the math didn't add up. It
    didn't, visibly: the middle two bands (decent, watchlist) were 222 names the line never
    mentioned. Printing only the extremes makes a complete number look like a broken one."""
    c = {"snapshot_date": "2026-03-20", "model_version": "v0.5", "horizon": "120d",
         "n": 515, "strong_hit_pct": None, "strong_n": 6, "weak_hit_pct": 42.5,
         "weak_n": 287, "middle_n": 222, "spread_pts": None, "low_confidence": False}
    line = journal._render_cohort_lines([c])[0]
    assert "515 stocks" in line and "222 mid-ranked" in line
    assert "too few to score" in line


def test_the_spread_is_stated_not_left_as_arithmetic():
    """Strong-minus-weak IS the claim being tested. Leaving the reader to subtract two percentages
    buries the one number that matters."""
    c = {"snapshot_date": "2026-08-13", "model_version": "v0.5", "horizon": "20d",
         "n": 1513, "strong_hit_pct": 52.1, "strong_n": 41, "weak_hit_pct": 46.7,
         "weak_n": 615, "middle_n": 857, "spread_pts": 5.4, "low_confidence": False}
    line = journal._render_cohort_lines([c])[0]
    assert "Spread: **+5.4 pts**" in line


def test_middle_count_is_derived_from_the_graded_total():
    """middle_n must come from n minus the two graded buckets, so it can never disagree with the
    numbers printed beside it."""
    cal = _syn_calendar(20)
    rows = []
    for i in range(25):   # strong
        rows.append({"backfilled": 0, "run_date": cal[0], "ticker": f"S{i}",
                     "score_5d": 90, "future_excess_return_5d": 0.01})
    for i in range(30):   # weak
        rows.append({"backfilled": 0, "run_date": cal[0], "ticker": f"W{i}",
                     "score_5d": 10, "future_excess_return_5d": -0.01})
    for i in range(12):   # decent / watchlist — graded total, but not in either bucket
        rows.append({"backfilled": 0, "run_date": cal[0], "ticker": f"M{i}",
                     "score_5d": 70, "future_excess_return_5d": 0.01})
    cohorts = journal._grade_all_cohorts(rows, cal)
    c = journal._matured_cohorts_section(cohorts, cal[5])["cohorts"][0]
    assert c["n"] == 67 and c["strong_n"] == 25 and c["weak_n"] == 30
    assert c["middle_n"] == 12
    assert c["spread_pts"] == round(100.0 - 0.0, 1)


def test_cohort_reports_money_not_only_skill():
    """"Beat its sector" measures whether the RANKING has skill, not whether you made money — a
    stock down 15% while its sector is down 20% scores as a hit. The owner read the log as a profit
    report and was misled by exactly that gap.

    So the line leads with the basket a person would actually buy and the two questions they
    actually have, and labels the sector-relative number as the skill measure it is."""
    c = {"snapshot_date": "2026-03-24", "model_version": "v0.5", "horizon": "120d",
         "n": 766, "strong_hit_pct": None, "strong_n": 9, "weak_hit_pct": 46.0,
         "weak_n": 415, "middle_n": 342, "spread_pts": None, "low_confidence": False,
         "top_picks": {"top_n": 10, "avg_return_pct": 18.42, "made_money_pct": 90.0,
                       "avg_vs_index_pct": 7.85, "beat_index_pct": 70.0}}
    line = journal._render_cohort_lines([c])[0]
    assert "If you had bought the top 10" in line
    assert "+18.4%" in line and "made money 90%" in line
    assert "+7.8% vs SPY" in line
    assert "Beat their sector" in line, "the skill measure must be labelled, not left unqualified"


def test_top_picks_are_graded_instead_of_the_strong_label_band():
    """The band was the wrong unit and it silently hid the money view entirely.

    "strong" is a fixed threshold (score >= 80). On a real day only 2-16 names clear it, so a
    per-day bucket almost never reached the 20 needed to report a rate — every money line in the
    live log rendered as nothing at all. The top-N basket is always exactly N, needs no
    minimum-sample gate, and is what a person would actually do with a ranked list."""
    rows = [{"run_date": "D0", "ticker": f"T{i}", "score_120d": float(100 - i),
             "future_return_120d": 0.10 if i < 8 else -0.05,
             "future_excess_vs_index_120d": 0.04 if i < 7 else -0.02,
             "future_excess_return_120d": 0.01} for i in range(40)]
    tp = journal._grade_top_picks(rows, 120, top_n=10)
    assert tp["top_n"] == 10
    assert tp["made_money_pct"] == 80.0          # 8 of the 10 highest-scored were up
    assert tp["beat_index_pct"] == 70.0          # 7 of 10 beat the index
    assert tp["avg_return_pct"] == round(100 * (8 * 0.10 + 2 * -0.05) / 10, 2)
    # Only 3 names that can be graded -> the basket cannot be filled, so no number is invented.
    assert journal._grade_top_picks(rows[:3], 120, top_n=10) is None


def test_entered_exited_compares_the_same_column_the_top10_is_ranked_on():
    """A near-miss when the display horizon moved 20d -> 120d.

    Today's top-10 is ranked on the display column; the previous run's scores were loaded on a
    hardcoded `score_20d`. Comparing two different rankings reports names as "entered" and "exited"
    that never moved — daily churn invented out of a column mismatch, with nothing to reveal it."""
    db = _temp_db()
    storage.init_db(db)
    col = journal.display_score_column()
    other = "score_5d" if col != "score_5d" else "score_20d"
    # Same ranking on the display column both days; the DECOY column is ordered the opposite way.
    for run_date in ("2026-07-01", "2026-07-04"):
        for tkr, s in {"AAA": 90.0, "BBB": 80.0, "CCC": 70.0}.items():
            storage.upsert_feature_snapshot({
                "run_date": run_date, "ticker": tkr, "benchmark": "SPY",
                "model_version": "v0.2_fundamentals_added", "backfilled": 0,
                "earnings_risk_unknown": 1, col: s, other: 100.0 - s,
                "timestamp_fetched": "2026-07-04T00:00:00Z",
            }, db_path=db)
    entry = journal.run_journal(_run_context(), db_path=db, output_dir=tempfile.mkdtemp())
    mv = entry["todays_rankings"]
    assert mv["compared_to_prev_live_run"] == "2026-07-01"
    assert mv["entered_top_10"] == [] and mv["exited_top_10"] == [], (
        "the ranking did not change, so nothing entered or exited")


def test_benchmark_etfs_are_not_recommended_as_picks():
    """SMH and QQQ turned up inside the "top 10 picks" for 2026-06-18 — the model recommending the
    yardstick it is measured against. Section 1 has always excluded benchmark ETFs from its
    displayed top 10; the basket grading did not, so the log's money numbers described a portfolio
    nobody would hold.

    They stay in the hit-rate buckets, which are about the ranking as a whole."""
    rows = [{"run_date": "D0", "ticker": t, "score_60d": s, "future_return_60d": r,
             "future_excess_vs_index_60d": r, "future_excess_return_60d": 0.0}
            for t, s, r in [("SMH", 99.0, -0.20), ("QQQ", 98.0, -0.10),
                            ("AAA", 97.0, 0.30), ("BBB", 96.0, 0.20), ("CCC", 95.0, 0.10)]]
    with_etfs = journal._grade_top_picks(rows, 60, top_n=3)
    without = journal._grade_top_picks(rows, 60, top_n=3, exclude=frozenset({"SMH", "QQQ"}))
    assert with_etfs["made_money_pct"] == round(100 / 3, 1)     # SMH, QQQ drag it down
    assert without["made_money_pct"] == 100.0                   # the three real names all rose
    assert without["avg_return_pct"] == 20.0
