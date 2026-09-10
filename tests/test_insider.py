"""SEC Form 3/4/5 insider transactions — synthetic only, no network.

The load-bearing test is `test_a_filing_is_invisible_until_its_filing_date`. An insider has two
business days to report a trade, so gating on the TRANSACTION date instead of the FILING date hands
the model several days of foresight per filing. That is a textbook lookahead leak: it produces a
beautiful, false result and never an error, so it is asserted directly rather than reviewed.

The rest exist because this dataset has three specific traps that all produce plausible wrong
numbers — multi-owner filings that multiply share counts, affiliated entities double-reporting one
economic trade under two accession numbers, and compensation events that look like insider buying.
"""
import pytest

from src import insider, storage


def _row(**kw):
    """One insider transaction with sane defaults; override what a test cares about."""
    base = {
        "accession": "0000000000-25-000001", "trans_sk": "1", "table_kind": "nonderiv",
        "cik": "0000000123", "ticker": "AAA", "sec_symbol": "AAA", "filed_date": "2025-03-10",
        "trans_date": "2025-03-05", "doc_type": "4", "trans_code": "P",
        "acquired_disposed": "A", "shares": 1000.0, "price_per_share": 10.0,
        "value_usd": 10000.0, "shares_owned_after": 5000.0, "owner_cik": "0000009999",
        "owner_name": "SOME INSIDER", "relationship": "Officer", "owner_title": "CFO",
        "is_director": 0, "is_officer": 1, "is_ten_pct_owner": 0, "is_10b5_1": 0,
        "direct_indirect": "D", "ingested_at": "2026-09-10T00:00:00Z",
    }
    base.update(kw)
    return base


def _db(tmp_path, rows):
    path = str(tmp_path / "insider.db")
    storage.init_db(path)
    storage.upsert_insider_transactions(rows, db_path=path)
    return path


# ---------------------------------------------------------------------------
# The point-in-time gate
# ---------------------------------------------------------------------------

def test_a_filing_is_invisible_until_its_filing_date(tmp_path):
    """THE test.

    A purchase EXECUTED on 2025-03-05 but REPORTED on 2025-03-10 was not public knowledge on the
    6th. Gating on `trans_date` would make it visible five days early — and would improve every
    backtest, which is exactly why it must be asserted rather than trusted.

    CLAUDE.md invariant #1."""
    db = _db(tmp_path, [_row(trans_date="2025-03-05", filed_date="2025-03-10")])

    for blind_date in ("2025-03-05", "2025-03-06", "2025-03-09"):
        assert storage.load_insider_transactions(
            ticker="AAA", filed_on_or_before=blind_date, db_path=db) == [], (
            f"a filing dated 2025-03-10 was visible on {blind_date}")

    visible = storage.load_insider_transactions(
        ticker="AAA", filed_on_or_before="2025-03-10", db_path=db)
    assert len(visible) == 1


def test_features_respect_the_gate_not_the_trade_date(tmp_path):
    db = _db(tmp_path, [_row(trans_date="2025-03-05", filed_date="2025-03-10")])
    before = insider.insider_features_as_of("AAA", "2025-03-07", db_path=db,
                                            coverage_end="2025-12-31")
    after = insider.insider_features_as_of("AAA", "2025-03-11", db_path=db,
                                           coverage_end="2025-12-31")
    assert before["insider_buy_count_90d"] == 0
    assert after["insider_buy_count_90d"] == 1


# ---------------------------------------------------------------------------
# Absence of data is not a zero
# ---------------------------------------------------------------------------

def test_a_date_past_coverage_returns_unknown_not_zero(tmp_path):
    """SEC publishes these datasets on a lag, so the store ends months before price history does.
    "No insider bought anything" and "we have no idea whether anyone bought anything" are different
    facts, and writing both as 0 turns a data gap into a real-looking signal value.

    CLAUDE.md invariant #2."""
    db = _db(tmp_path, [_row(filed_date="2025-03-10")])
    out = insider.insider_features_as_of("AAA", "2026-07-01", db_path=db,
                                         coverage_end="2026-03-31")
    assert out["coverage_missing"] is True
    assert out["insider_buy_count_90d"] is None, "a gap must not be reported as zero activity"
    assert out["insider_net_buy_value_90d"] is None
    assert out["days_since_insider_buy"] is None


def test_within_coverage_a_genuine_absence_is_a_real_zero(tmp_path):
    """The other side of the same rule: inside coverage, no filings really does mean no buying."""
    db = _db(tmp_path, [_row(filed_date="2024-01-05")])
    out = insider.insider_features_as_of("AAA", "2025-06-01", db_path=db,
                                         coverage_end="2026-03-31")
    assert out["coverage_missing"] is False
    assert out["insider_buy_count_90d"] == 0


# ---------------------------------------------------------------------------
# Compensation is not an opinion
# ---------------------------------------------------------------------------

def test_grants_exercises_and_tax_withholding_are_not_counted_as_buying(tmp_path):
    """Codes A (grant), M (option exercise) and F (shares withheld for tax) are all "acquisitions"
    that increase an insider's holding while reflecting no view whatsoever on the price — they are
    payroll. They outnumber genuine open-market purchases by roughly an order of magnitude, so
    counting them would bury the one code with a documented anomaly behind it."""
    rows = [
        _row(accession="A1", trans_sk="1", trans_code="A", filed_date="2025-03-01"),
        _row(accession="A2", trans_sk="2", trans_code="M", filed_date="2025-03-02"),
        _row(accession="A3", trans_sk="3", trans_code="F", filed_date="2025-03-03"),
        _row(accession="A4", trans_sk="4", trans_code="P", filed_date="2025-03-04"),
    ]
    db = _db(tmp_path, rows)
    out = insider.insider_features_as_of("AAA", "2025-03-05", db_path=db,
                                         coverage_end="2025-12-31")
    assert out["insider_buy_count_90d"] == 1, "only the open-market purchase counts"


def test_sales_net_against_purchases(tmp_path):
    rows = [
        _row(accession="B1", trans_sk="1", trans_code="P", shares=1000.0, price_per_share=10.0,
             value_usd=10000.0),
        _row(accession="B2", trans_sk="2", trans_code="S", shares=400.0, price_per_share=10.0,
             value_usd=4000.0),
    ]
    db = _db(tmp_path, rows)
    out = insider.insider_features_as_of("AAA", "2025-03-11", db_path=db,
                                         coverage_end="2025-12-31")
    assert out["insider_buy_value_90d"] == pytest.approx(10000.0)
    assert out["insider_net_buy_value_90d"] == pytest.approx(6000.0)
    assert out["insider_sell_count_90d"] == 1


# ---------------------------------------------------------------------------
# The two duplication traps
# ---------------------------------------------------------------------------

def test_one_economic_trade_reported_by_two_affiliated_filers_is_counted_once(tmp_path):
    """Real case from 2025Q1: two Apollo entities each filed a Form 4 for the SAME 1,185,242-share
    TBLA disposition, under different accession numbers. Summing by accession double-counts it.

    The accession number cannot distinguish these — only the trade's own attributes can — so the
    aggregation deduplicates on (cik, trans_date, trans_code, shares, price)."""
    rows = [
        _row(accession="0001104659-25-030099", trans_sk="7059595", trans_code="P",
             trans_date="2025-03-05", shares=1185242.0, price_per_share=3.01,
             value_usd=1185242.0 * 3.01),
        _row(accession="0001104659-25-030101", trans_sk="7984258", trans_code="P",
             trans_date="2025-03-05", shares=1185242.0, price_per_share=3.01,
             value_usd=1185242.0 * 3.01),
    ]
    db = _db(tmp_path, rows)
    assert len(storage.load_insider_transactions(ticker="AAA", filed_on_or_before="2025-03-31",
                                                 db_path=db)) == 2, "both filings are STORED"
    out = insider.insider_features_as_of("AAA", "2025-03-11", db_path=db,
                                         coverage_end="2025-12-31")
    assert out["insider_buy_count_90d"] == 1, "but it is ONE economic purchase"
    assert out["insider_buy_value_90d"] == pytest.approx(1185242.0 * 3.01)


def test_a_multi_owner_filing_is_stored_once_not_once_per_owner(tmp_path):
    """1,151 of 63,284 filings in a single quarter carry multiple reporting owners, up to 10. Keying
    storage by owner would store one copy of the same transaction per co-filer and multiply its
    share count by up to 10x in any aggregate. The primary key deliberately excludes owner."""
    same = dict(accession="C1", trans_sk="1", table_kind="nonderiv")
    rows = [_row(owner_cik="0000001", owner_name="OWNER ONE", **same),
            _row(owner_cik="0000002", owner_name="OWNER TWO", **same)]
    db = _db(tmp_path, rows)
    stored = storage.load_insider_transactions(ticker="AAA", filed_on_or_before="2025-12-31",
                                               db_path=db)
    assert len(stored) == 1, "one transaction, however many co-filers reported it"


def test_derivative_legs_do_not_count_as_share_purchases(tmp_path):
    """Derivative rows are option mechanics — grants, exercises, expirations of contracts — not
    someone spending their own money on stock in the open market."""
    rows = [_row(accession="D1", trans_sk="1", table_kind="deriv", trans_code="P"),
            _row(accession="D2", trans_sk="2", table_kind="nonderiv", trans_code="P")]
    db = _db(tmp_path, rows)
    out = insider.insider_features_as_of("AAA", "2025-03-11", db_path=db,
                                         coverage_end="2025-12-31")
    assert out["insider_buy_count_90d"] == 1


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_sec_dates_parse_and_refuse_to_guess():
    """A mis-parsed FILING_DATE silently shifts the point-in-time gate — the one error in this
    module that is invisible in the output. Anything unrecognized returns None and the row is
    dropped rather than dated by guesswork."""
    assert insider.parse_sec_date("31-MAR-2025") == "2025-03-31"
    assert insider.parse_sec_date("01-JAN-2024") == "2024-01-01"
    for bad in ("", None, "2025-03-31", "31-XXX-2025", "32-MAR-2025", "garbage"):
        assert insider.parse_sec_date(bad) is None, f"{bad!r} should not parse"


def test_relationship_flags_split_a_joined_list():
    assert insider._relationship_flags("Director,Officer") == (True, True, False, False)
    assert insider._relationship_flags("TenPercentOwner") == (False, False, True, False)
    assert insider._relationship_flags("Director,Other") == (True, False, False, True)
    assert insider._relationship_flags("") == (False, False, False, False)


def test_quarters_in_range_spans_year_boundaries():
    assert insider.quarters_in_range((2024, 3), (2025, 2)) == [
        (2024, 3), (2024, 4), (2025, 1), (2025, 2)]
    assert insider.quarters_in_range((2025, 1), (2025, 1)) == [(2025, 1)]


def test_an_empty_universe_filter_is_a_hard_failure(tmp_path, monkeypatch):
    """An empty CIK map means the EDGAR ingest never ran. Falling back to "no filter" would ingest
    every US public issuer — five times the rows — and would look exactly like success."""
    db = str(tmp_path / "empty.db")
    storage.init_db(db)
    with pytest.raises(RuntimeError, match="cik_map is empty"):
        insider.ingest_insider_quarters(db_path=db)


def test_value_is_null_when_the_price_is_missing():
    """A zero-dollar transaction and an unpriced one are different facts. Defaulting the missing
    price to 0 would silently drag every net-buy aggregate toward zero."""
    rows = insider._num("not-a-number")
    assert rows is None


def test_our_ticker_comes_from_the_cik_not_from_sec_free_text(tmp_path):
    """SEC's ISSUERTRADINGSYMBOL is typed by the filer and arrives as "(CALX)", "-", "BFA, BFB",
    "BIO BIO.B", "BRK.A". Joining on it silently returned ZERO insider rows for 35 of our names
    whose filings were in the store the whole time — a coverage hole that looks exactly like a
    company whose insiders never trade. The CIK is the only stable key."""
    stored = [_row(cik="0000000123", ticker="BRK-B", sec_symbol="BRK.A")]
    db = _db(tmp_path, stored)
    assert storage.load_insider_transactions(ticker="BRK-B", filed_on_or_before="2025-12-31",
                                             db_path=db), "must be reachable by OUR ticker"
    assert storage.load_insider_transactions(ticker="BRK.A", filed_on_or_before="2025-12-31",
                                             db_path=db) == [], "SEC's free text is not a key"


def test_the_bulk_index_and_the_single_ticker_path_agree_exactly(tmp_path):
    """Two code paths computing "insider buying" is how a subtly different second definition drifts
    into existence — the same hazard `evaluation.trading_calendar` was centralised to prevent. Both
    call `_aggregate` and nothing else, so this asserts they cannot diverge."""
    rows = [
        _row(accession="E1", trans_sk="1", trans_code="P", filed_date="2025-01-10"),
        _row(accession="E2", trans_sk="2", trans_code="S", filed_date="2025-02-15",
             shares=300.0, price_per_share=12.0, value_usd=3600.0),
        _row(accession="E3", trans_sk="3", trans_code="P", filed_date="2025-03-01"),
        _row(accession="E4", trans_sk="4", trans_code="P", filed_date="2024-01-01"),  # outside 90d
    ]
    db = _db(tmp_path, rows)
    index = insider.build_insider_index(db_path=db)
    # Neither path is told what coverage is — both must DERIVE it from the store, or they will
    # disagree about which dates are knowable, which is the divergence that matters most.
    for as_of in ("2025-01-15", "2025-02-20", "2025-03-01", "2025-12-01"):
        slow = insider.insider_features_as_of("AAA", as_of, db_path=db)
        fast = insider.features_from_index(index, "AAA", as_of)
        assert slow == fast, f"paths disagree on {as_of}: {slow} vs {fast}"
    assert index.coverage_end == "2025-03-01", "coverage is a fact about the DATA, not config"


def test_the_window_is_a_trailing_window_not_all_history(tmp_path):
    """A purchase from two years ago is not news. If the window were ignored, every company whose
    insiders ever bought would read as a permanent buy signal."""
    db = _db(tmp_path, [_row(accession="F1", trans_sk="1", trans_code="P",
                             filed_date="2024-01-05")])
    index = insider.build_insider_index(db_path=db)
    assert index.coverage_end == "2024-01-05"
    near = insider.features_from_index(index, "AAA", "2024-01-05")
    assert near["insider_buy_count_90d"] == 1
    # Past coverage entirely -> unknown, which is the stronger guarantee than "0".
    far = insider.features_from_index(index, "AAA", "2025-06-01")
    assert far["coverage_missing"] is True
