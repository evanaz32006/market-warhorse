"""SEC filing index / 8-K material events — synthetic only, no network.

The load-bearing test is `test_a_filing_accepted_after_the_close_is_not_actionable_until_tomorrow`.
An 8-K accepted at 16:35 ET carries that day's `filingDate` but the market was already shut, so
treating it as knowable at that day's close reads a headline before it was published. It is a
one-day lookahead — small, entirely invisible in the output, and exactly the size that flatters a
short-horizon event study.

The other theme is that "an 8-K happened" is nearly meaningless: item 9.01 is an attachment notice
and 5.07 is the annual shareholder vote. Treating those as material events is the same error as
counting an option grant as insider buying.
"""
import pytest

from src import filings, storage


def _cal(days):
    return list(days)


def _row(**kw):
    base = {
        "accession": "0000320193-26-000018", "cik": "0000320193", "ticker": "AAPL",
        "form": "8-K", "filed_date": "2026-07-30",
        "acceptance_datetime": "2026-07-30T09:30:00.000-04:00",
        "report_date": "2026-07-30", "items": "2.02,9.01", "primary_doc": "8k.htm",
        "ingested_at": "2026-09-10T00:00:00Z",
    }
    base.update(kw)
    return base


def _db(tmp_path, rows, ingested_through="2026-09-10"):
    """A store plus the ingest marker a COMPLETED run would have written.

    Coverage deliberately does NOT come from MAX(filed_date): with 1,500 companies somebody files
    every business day, so a run that fetched three companies and died would still look current.
    Tests set the marker because that is what production does."""
    path = str(tmp_path / "f.db")
    storage.init_db(path)
    storage.upsert_sec_filings(rows, db_path=path)
    if ingested_through:
        storage.set_meta(storage.SEC_FILINGS_INGEST_MARKER, ingested_through, db_path=path)
    return path


# ---------------------------------------------------------------------------
# The point-in-time roll
# ---------------------------------------------------------------------------

def test_a_filing_accepted_after_the_close_is_not_actionable_until_tomorrow():
    """THE test.

    SEC stamps an 8-K accepted at 16:35 ET with THAT DAY's filingDate. The market shut at 16:00.
    Anything that treats the filing as knowable at that day's close is trading on a headline before
    it was published — a one-day leak, invisible in every output, and precisely the size that makes
    a short-horizon event study look real."""
    cal = _cal(["2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03"])
    after = filings.effective_date("2026-07-30", "2026-07-30T16:35:00.000-04:00", cal)
    before = filings.effective_date("2026-07-30", "2026-07-30T09:30:00.000-04:00", cal)
    assert after == "2026-07-31", "an after-close filing must roll to the next session"
    assert before == "2026-07-30", "an intraday filing is actionable at that day's close"


def test_a_weekend_filing_rolls_forward_to_the_next_session():
    """Friday-evening and weekend filings are a real and deliberate corporate habit. Rolling them to
    'Saturday' would place an event on a date with no price, which quietly drops it."""
    cal = _cal(["2026-07-31", "2026-08-03", "2026-08-04"])   # Fri, Mon, Tue
    assert filings.effective_date(
        "2026-08-01", "2026-08-01T11:00:00.000-04:00", cal) == "2026-08-03"
    assert filings.effective_date(
        "2026-07-31", "2026-07-31T18:00:00.000-04:00", cal) == "2026-08-03"


def test_an_unparseable_timestamp_falls_back_rather_than_guessing():
    """A wrong time is worse than no time: it shifts the gate by a day silently. With no usable
    timestamp the filing date is used as-is and rolled onto the calendar, never invented."""
    cal = _cal(["2026-07-30", "2026-07-31"])
    assert filings.effective_date("2026-07-30", "not-a-timestamp", cal) == "2026-07-30"
    assert filings.effective_date("2026-07-30", None, cal) == "2026-07-30"


def test_a_filing_whose_first_session_has_not_happened_yet_is_none():
    """Better to return nothing than to attach the event to the last date we happen to have."""
    cal = _cal(["2026-07-29", "2026-07-30"])
    assert filings.effective_date("2026-07-30", "2026-07-30T17:00:00.000-04:00", cal) is None


# ---------------------------------------------------------------------------
# Routine is not material
# ---------------------------------------------------------------------------

def test_paperwork_only_filings_are_not_material_events():
    """9.01 is 'financial statements and exhibits' — an attachment notice bolted onto most other
    items. 5.07 is the annual shareholder vote. An 8-K carrying only those is administrative."""
    assert filings.is_material("9.01") is False
    assert filings.is_material("5.07") is False
    assert filings.is_material("5.07,9.01") is False
    assert filings.is_material("") is False
    assert filings.is_material(None) is False
    # ...but the same attachment alongside a real item does not neutralise it.
    assert filings.is_material("2.02,9.01") is True
    assert filings.is_material("4.02") is True


def test_parse_items_handles_the_comma_joined_string():
    assert filings.parse_items("2.02,9.01") == {"2.02", "9.01"}
    assert filings.parse_items(" 5.02 , 7.01 ") == {"5.02", "7.01"}
    assert filings.parse_items(None) == set()


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

def test_event_counts_use_the_effective_date_not_the_filing_date(tmp_path):
    """The whole point of the roll, asserted end to end: an 8-K accepted after Thursday's close must
    not appear in Thursday's feature row."""
    cal = _cal(["2026-07-29", "2026-07-30", "2026-07-31"])
    db = _db(tmp_path, [_row(accession="A1", filed_date="2026-07-30",
                             acceptance_datetime="2026-07-30T16:45:00.000-04:00",
                             items="2.02")])
    index = filings.build_event_index(db_path=db, calendar=cal)
    on_the_day = filings.event_features_as_of(index, "AAPL", "2026-07-30")
    next_day = filings.event_features_as_of(index, "AAPL", "2026-07-31")
    assert on_the_day["material_8k_5d"] == 0, "not actionable until the next session"
    assert next_day["material_8k_5d"] == 1


def test_routine_filings_do_not_inflate_the_material_count(tmp_path):
    cal = _cal(["2026-07-%02d" % d for d in range(1, 32)])
    rows = [
        _row(accession="R1", filed_date="2026-07-10", items="5.07,9.01",
             acceptance_datetime="2026-07-10T10:00:00.000-04:00"),
        _row(accession="R2", filed_date="2026-07-12", items="9.01",
             acceptance_datetime="2026-07-12T10:00:00.000-04:00"),
        _row(accession="R3", filed_date="2026-07-15", items="5.02",
             acceptance_datetime="2026-07-15T10:00:00.000-04:00"),
    ]
    db = _db(tmp_path, rows)
    index = filings.build_event_index(db_path=db, calendar=cal)
    out = filings.event_features_as_of(index, "AAPL", "2026-07-20")
    assert out["disclosure_8k_30d"] + out["material_8k_30d"] >= 1
    assert out["material_8k_30d"] == 1, "but only one of them said anything"
    assert out["days_since_material_8k"] == 5


def test_the_red_flag_items_are_picked_out(tmp_path):
    """4.02 (previously issued financials cannot be relied upon), 2.06 (material impairment),
    1.03 (bankruptcy) and 3.01 (delisting) are the rare, severe ones. They must not be diluted into
    a generic count where 200 routine filings drown them."""
    cal = _cal(["2026-07-%02d" % d for d in range(1, 32)])
    db = _db(tmp_path, [
        _row(accession="X1", filed_date="2026-07-05", items="4.02",
             acceptance_datetime="2026-07-05T10:00:00.000-04:00"),
        _row(accession="X2", filed_date="2026-07-06", items="8.01",
             acceptance_datetime="2026-07-06T10:00:00.000-04:00"),
    ])
    index = filings.build_event_index(db_path=db, calendar=cal)
    out = filings.event_features_as_of(index, "AAPL", "2026-07-20")
    assert out["redflag_8k_90d"] == 1
    assert out["material_8k_30d"] == 2


def test_a_date_past_coverage_returns_unknown_not_zero(tmp_path):
    """Same rule as the insider store: "no 8-K was filed" and "we have no filing data for this
    period" are different facts, and writing both as 0 turns a gap into a signal."""
    cal = _cal(["2026-07-%02d" % d for d in range(1, 32)])
    db = _db(tmp_path, [_row(accession="C1", filed_date="2026-07-05",
                             acceptance_datetime="2026-07-05T10:00:00.000-04:00")],
             ingested_through="2026-07-31")
    index = filings.build_event_index(db_path=db, calendar=cal)
    out = filings.event_features_as_of(index, "AAPL", "2026-08-15")
    assert out["coverage_missing"] is True
    assert out["material_8k_30d"] is None
    assert out["material_8k_30d"] is None


def test_only_requested_forms_are_parsed():
    """The store is deliberately narrow. A block containing a Form 4 must not leak into an 8-K
    count — Form 4 already lives in `insider_transactions` with far more detail."""
    block = {
        "accessionNumber": ["A", "B", "C"],
        "form": ["8-K", "4", "10-Q"],
        "filingDate": ["2026-07-01", "2026-07-02", "2026-07-03"],
        "acceptanceDateTime": ["2026-07-01T10:00:00.000-04:00"] * 3,
        "reportDate": ["", "", ""],
        "items": ["2.02", "", ""],
        "primaryDocument": ["a.htm", "b.xml", "c.htm"],
    }
    rows = filings._rows_from_block(block, "0000000123", "AAA", {"8-K", "10-Q"}, None)
    assert {r["form"] for r in rows} == {"8-K", "10-Q"}
    assert len(rows) == 2


def test_filings_before_the_since_date_are_dropped():
    block = {
        "accessionNumber": ["A", "B"],
        "form": ["8-K", "8-K"],
        "filingDate": ["2020-01-01", "2026-07-01"],
        "acceptanceDateTime": ["2020-01-01T10:00:00.000-05:00",
                               "2026-07-01T10:00:00.000-04:00"],
        "reportDate": ["", ""], "items": ["8.01", "8.01"],
        "primaryDocument": ["a.htm", "b.htm"],
    }
    rows = filings._rows_from_block(block, "0000000123", "AAA", {"8-K"}, "2023-12-01")
    assert len(rows) == 1 and rows[0]["filed_date"] == "2026-07-01"


def test_an_empty_cik_map_is_a_hard_failure(tmp_path):
    """Would otherwise look like a successful run over zero companies."""
    db = str(tmp_path / "empty.db")
    storage.init_db(db)
    with pytest.raises(RuntimeError, match="cik_map is empty"):
        filings.ingest_filings(db_path=db)


def test_a_half_finished_ingest_does_not_look_current(tmp_path):
    """MAX(filed_date) is a bad coverage signal for this store: with 1,500 companies somebody files
    every business day, so a run that fetched three companies and then died would still report the
    store as current. Coverage gates on the marker a COMPLETED ingest writes, so a crashed run
    leaves the previous — honest — boundary in place."""
    cal = _cal(["2026-09-%02d" % d for d in range(1, 12)])
    rows = [_row(accession="P1", filed_date="2026-09-09",
                 acceptance_datetime="2026-09-09T10:00:00.000-04:00")]
    stale = _db(tmp_path, rows, ingested_through="2026-08-01")
    index = filings.build_event_index(db_path=stale, calendar=cal)
    out = filings.event_features_as_of(index, "AAPL", "2026-09-09")
    assert out["coverage_missing"] is True, (
        "a fresh filing from one company must not vouch for the whole universe")
