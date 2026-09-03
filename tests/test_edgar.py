"""EDGAR point-in-time fundamentals (v0.4). All synthetic — no network. Covers the invariants that
make the reconstruction legitimate: filed-date gating (no-lookahead), originally-filed-wins (not
restated), correct TTM for US filers, tag-fallback chains, financial-profile sit-out, and CIK mapping."""
from src import edgar, storage


def _fact(tag, end, value, filed, start="", fy=None, fp=None, taxonomy="us-gaap", unit="USD", accn=None):
    return {"cik": "C", "ticker": "T", "taxonomy": taxonomy, "tag": tag, "unit": unit,
            "period_start": start, "period_end": end, "fiscal_year": fy, "fiscal_period": fp,
            "value": value, "form": "10-Q", "accession": accn or f"{tag}-{start}-{end}-{filed}",
            "filed_date": filed, "ingested_at": "t"}


def _db(tmp_path):
    db = str(tmp_path / "edgar.db"); storage.init_db(db); return db


def test_filed_date_gating_no_lookahead(tmp_path):
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("StockholdersEquity", "2024-03-31", 1000, filed="2024-05-01"),   # filed AFTER as-of D
        _fact("StockholdersEquity", "2023-12-31", 900, filed="2024-02-01"),    # filed before D
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-04-15", db_path=db)
    # the 2024-05-01 filing did not exist on 2024-04-15; latest usable equity is the 2023-12-31 one
    assert f["_provenance"]["equity"]["filed_date"] == "2024-02-01"
    assert f["_provenance"]["equity"]["period_end"] == "2023-12-31"


def test_restatement_earliest_filed_wins(tmp_path):
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("StockholdersEquity", "2023-12-31", 900, filed="2024-02-01", accn="orig"),
        _fact("StockholdersEquity", "2023-12-31", 950, filed="2024-08-01", accn="restate"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-09-01", price=1.0, db_path=db)   # both filed <= D
    assert f["_provenance"]["equity"]["filed_date"] == "2024-02-01"              # originally-filed, not restated


def test_ttm_annual_plus_ytd_noncalendar_fy(tmp_path):
    db = _db(tmp_path)
    # Fiscal year ends June 30. TTM revenue ending Dec-2023 = FY2023 annual + H1-FY2024 - H1-FY2023.
    storage.upsert_edgar_facts([
        _fact("Revenues", "2023-06-30", 1000, start="2022-07-01", filed="2023-08-01", fy=2023, fp="FY"),
        _fact("Revenues", "2023-12-31", 600, start="2023-07-01", filed="2024-02-01", fy=2024, fp="Q2"),  # H1 FY24
        _fact("Revenues", "2022-12-31", 500, start="2022-07-01", filed="2023-02-01", fy=2023, fp="Q2"),  # H1 FY23
        _fact("CommonStockSharesOutstanding", "2023-12-31", 100, filed="2024-02-01", unit="shares"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-03-01", price=10.0, db_path=db)  # mktcap = 10*100 = 1000
    assert f["_provenance"]["revenue"]["method"] == "ttm_annual_plus_ytd"
    assert f["price_to_sales"] == 1000 / (1000 + 600 - 500)                      # TTM revenue = 1100


def test_refuse_to_annualize_single_quarter(tmp_path):
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2024-03-31", 250, start="2024-01-01", filed="2024-05-01", fy=2024, fp="Q1"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", price=10.0, db_path=db)
    assert f["_provenance"]["revenue"] is None      # one quarter, no annual/YTD -> missing, never annualized
    assert f["price_to_sales"] is None


def test_tag_fallback_chain_resolves_and_logs(tmp_path):
    db = _db(tmp_path)
    # only the THIRD revenue fallback (SalesRevenueNet) is present
    storage.upsert_edgar_facts([
        _fact("SalesRevenueNet", "2023-12-31", 800, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", price=10.0, db_path=db)
    assert f["_provenance"]["revenue"]["tag"] == "SalesRevenueNet"


def test_financial_profile_sits_out_operating_margin(tmp_path, monkeypatch):
    # The exclusion list is switched OFF here so this exercises the FINANCIAL-PROFILE rule in isolation.
    # (operating_margin is gate-withheld in production — see test_gate_withheld_field_is_dropped.)
    monkeypatch.setattr(edgar, "EDGAR_EXCLUDED_FIELDS", set())
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2023-12-31", 1000, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
        _fact("OperatingIncomeLoss", "2023-12-31", 300, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
    ], db_path=db)
    ind = edgar.get_fundamentals_as_of("T", "2024-06-01", sector="Industrials", db_path=db)
    fin = edgar.get_fundamentals_as_of("T", "2024-06-01", sector="Financials", db_path=db)
    assert ind["operating_margin"] == 0.3           # comparable for an industrial
    assert fin["operating_margin"] is None          # not comparable for a bank/insurer -> sits out


def test_gate_withheld_field_is_dropped(tmp_path):
    """A field the Phase-3 gate could not confirm sits out rather than entering a score unverified.
    operating_margin is computable here (all legs present and aligned) and is still withheld: EDGAR's
    as-reported figure ran a systematic ~9% below yfinance's apparently-normalized one, and an
    unverified number does not get to move a ranking. Config-driven, so re-enabling is an edit."""
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2023-12-31", 1000, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
        _fact("OperatingIncomeLoss", "2023-12-31", 300, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", sector="Industrials", db_path=db)
    assert "operating_margin" in edgar.EDGAR_EXCLUDED_FIELDS
    assert f["operating_margin"] is None
    # the underlying concepts still resolve — provenance is kept for diagnosis and future re-enabling
    assert f["_provenance"]["operating_income"]["period_end"] == "2023-12-31"


def test_huge_fact_value_is_coerced_not_crashed(tmp_path):
    # Some filers report values (public float, share counts) larger than SQLite's 64-bit INTEGER range;
    # they must be coerced to float and stored, never crash the ingest with OverflowError.
    db = _db(tmp_path)
    huge = 2 ** 63 + 1000
    blob = {"facts": {"us-gaap": {"EntityPublicFloat": {"units": {"USD": [
        {"end": "2024-03-31", "val": huge, "accn": "A", "filed": "2024-05-01"}]}}}, "dei": {}}}
    rows = list(edgar._parse_company_facts("C", "T", blob))
    storage.upsert_edgar_facts(rows, db_path=db)          # must not raise
    got = storage.load_edgar_facts("T", db_path=db)
    assert len(got) == 1 and got[0]["value"] == float(huge)


def _bs(tag, end, value, filed, **kw):
    """A balance-sheet (instant) fact: no period_start."""
    return _fact(tag, end, value, filed, start="", **kw)


def test_debt_to_equity_uses_interest_bearing_debt_scaled_to_percent(tmp_path):
    # yfinance's debtToEquity = interest-bearing debt / equity * 100. NOT total liabilities, and NOT a
    # raw fraction. Total Liabilities here (5000) is deliberately far larger than real debt (400) so a
    # regression back to the old mapping produces an obviously different number.
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _bs("StockholdersEquity", "2024-03-31", 500, filed="2024-05-01"),
        _bs("LongTermDebtNoncurrent", "2024-03-31", 300, filed="2024-05-01"),
        _bs("LongTermDebtCurrent", "2024-03-31", 100, filed="2024-05-01"),
        _bs("Liabilities", "2024-03-31", 5000, filed="2024-05-01"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", db_path=db)
    assert f["debt_to_equity"] == 80.0            # (300+100)/500 * 100 — percent, not 0.8, not 1000.0
    assert f["_provenance"]["debt_total"]["debt_partial"] is False


def test_debt_partial_flagged_when_current_leg_missing(tmp_path):
    # A filer with no current-debt tag is NOT assumed to have zero short-term debt. The long-term leg
    # still yields a number, but it is flagged partial so an understated D/E stays auditable.
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _bs("StockholdersEquity", "2024-03-31", 500, filed="2024-05-01"),
        _bs("LongTermDebtNoncurrent", "2024-03-31", 300, filed="2024-05-01"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", db_path=db)
    assert f["debt_to_equity"] == 60.0
    assert f["_provenance"]["debt_total"]["debt_partial"] is True
    assert f["_provenance"]["debt_total"]["current"] is None   # recorded as absent, never imputed as 0


def test_debt_missing_when_long_term_leg_absent(tmp_path):
    # Only a current-debt tag: the dominant leg is missing, so the concept sits out entirely rather
    # than reporting a D/E built from a fraction of the debt.
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _bs("StockholdersEquity", "2024-03-31", 500, filed="2024-05-01"),
        _bs("DebtCurrent", "2024-03-31", 100, filed="2024-05-01"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", db_path=db)
    assert f["debt_to_equity"] is None
    assert f["_provenance"]["debt_total"] is None


def test_dead_tag_loses_to_fresher_tag_later_in_chain(tmp_path, monkeypatch):
    """THE NVDA REGRESSION TEST. A filer abandons its first-choice revenue tag but the old facts remain
    in EDGAR forever. First-tag-wins returned that stale annual with method='annual' and full confidence
    while operating income resolved to a current TTM — producing a 603% operating margin. The resolver
    must pick the FRESHEST candidate across the whole chain, not the first one that happens to hit."""
    monkeypatch.setattr(edgar, "EDGAR_EXCLUDED_FIELDS", set())   # assert on the 603% symptom itself
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        # chain position 1: abandoned after FY2022, but a complete annual still sits here
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", "2022-01-30", 26914,
              start="2021-01-31", filed="2022-03-18", fy=2022, fp="FY"),
        # chain position 2: the tag the filer actually uses now
        _fact("Revenues", "2024-01-28", 60922, start="2023-01-29", filed="2024-02-21", fy=2024, fp="FY"),
        _fact("OperatingIncomeLoss", "2024-01-28", 32972, start="2023-01-29",
              filed="2024-02-21", fy=2024, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", db_path=db)
    prov = f["_provenance"]["revenue"]
    assert prov["tag"] == "Revenues"                 # NOT the earlier, staler chain entry
    assert prov["period_end"] == "2024-01-28"
    assert prov["n_candidates"] == 2                 # both were evaluated; the fresher one won
    # the margin lands where it should instead of ~9x too high
    assert 0.5 < f["operating_margin"] < 0.6


def test_all_candidates_stale_yields_missing_not_ancient_value(tmp_path):
    # A filer that stopped reporting must SIT OUT. An ancient number presented as current is exactly
    # the "confident, beautiful lie" the staleness cap exists to prevent.
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2019-12-31", 1000, start="2019-01-01", filed="2020-02-01", fy=2019, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", price=10.0, db_path=db)
    assert f["price_to_sales"] is None
    prov = f["_provenance"]["revenue"]
    assert prov["missing_reason"] == "stale"          # diagnosable, not silently absent
    assert prov["n_stale_rejected"] == 1


def test_ttm_rejects_prior_ytd_with_mismatched_duration(tmp_path):
    """TTM = prior-FY annual + current YTD - prior-year YTD is only valid when the two YTD legs cover
    the SAME span. Matching on (fiscal_year-1, fiscal_period) alone can pair a 3-month current stub
    against a 9-month prior-year YTD, giving `annual + 3mo - 9mo` — a half-year undercount reported
    with full confidence. Mismatched legs must make the concept missing, not wrong."""
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2023-12-31", 1000, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
        # current leg is a 3-month Q3 stub...
        _fact("Revenues", "2024-09-30", 200, start="2024-07-01", filed="2024-11-01", fy=2024, fp="Q3"),
        # ...and the only prior-year Q3 fact is a 9-MONTH cumulative YTD. Not comparable.
        _fact("Revenues", "2023-09-30", 700, start="2023-01-01", filed="2023-11-01", fy=2023, fp="Q3"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-12-01", price=10.0, db_path=db)
    prov = f["_provenance"]["revenue"]
    # must NOT be the bogus roll-forward 1000 + 200 - 700 = 500
    assert prov is None or prov.get("method") != "ttm_annual_plus_ytd"


def test_margin_sits_out_when_its_two_legs_cover_different_periods(tmp_path, monkeypatch):
    """A margin divides one flow by another, so both legs must describe the SAME twelve months. Here
    revenue resolves to the FY2024 annual while operating income rolls forward a quarter further to
    2025-03-31. Dividing across that gap yields a plausible-looking number that means nothing, so the
    margin must sit out. 51 of 507 real filers hit this — a milder cousin of the NVDA 603% bug."""
    monkeypatch.setattr(edgar, "EDGAR_EXCLUDED_FIELDS", set())   # test alignment, not the gate exclusion
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        # revenue: only an annual through 2024-12-31
        _fact("Revenues", "2024-12-31", 1000, start="2024-01-01", filed="2025-02-01", fy=2024, fp="FY"),
        # operating income: annual PLUS a Q1-2025 roll-forward, so its TTM ends 2025-03-31
        _fact("OperatingIncomeLoss", "2024-12-31", 200, start="2024-01-01",
              filed="2025-02-01", fy=2024, fp="FY"),
        _fact("OperatingIncomeLoss", "2025-03-31", 60, start="2025-01-01",
              filed="2025-05-01", fy=2025, fp="Q1"),
        _fact("OperatingIncomeLoss", "2024-03-31", 50, start="2024-01-01",
              filed="2024-05-01", fy=2024, fp="Q1"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2025-06-01", sector="Industrials", db_path=db)
    prov = f["_provenance"]
    assert prov["revenue"]["period_end"] == "2024-12-31"
    assert prov["operating_income"]["period_end"] == "2025-03-31"   # legs genuinely differ
    assert f["operating_margin"] is None                            # so the ratio refuses to compute


def test_negative_equity_sits_out_rather_than_inverting_the_quality_rank(tmp_path):
    """Negative book equity (buyback-heavy names like CLX, DVA) makes debt/equity strongly NEGATIVE.
    debt_to_equity is an INVERTED quality field — lower is better — so a -3,700 would rank the most
    levered company in the index as its safest. Undefined, therefore missing, never a fake number."""
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _bs("StockholdersEquity", "2024-03-31", -200, filed="2024-05-01"),
        _bs("LongTermDebtNoncurrent", "2024-03-31", 5000, filed="2024-05-01"),
        _fact("NetIncomeLoss", "2024-03-31", 300, start="2023-04-01", filed="2024-05-01",
              fy=2024, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2024-06-01", db_path=db)
    assert f["debt_to_equity"] is None
    assert f["return_on_equity"] is None


def test_revenue_prefers_total_over_contract_only_tag(tmp_path):
    """REITs tag both `Revenues` (the total) and RevenueFromContractWithCustomer... (ASC-606 contract
    revenue only — a sliver, since leases are not contracts with customers). Preferring the contract tag
    understated AVB's revenue enough to give it a 160x profit margin. The total must win."""
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _fact("Revenues", "2024-12-31", 2800, start="2024-01-01", filed="2025-02-01", fy=2024, fp="FY"),
        _fact("RevenueFromContractWithCustomerExcludingAssessedTax", "2024-12-31", 40,
              start="2024-01-01", filed="2025-02-01", fy=2024, fp="FY"),
        _fact("NetIncomeLoss", "2024-12-31", 1100, start="2024-01-01", filed="2025-02-01",
              fy=2024, fp="FY"),
    ], db_path=db)
    f = edgar.get_fundamentals_as_of("T", "2025-06-01", db_path=db)
    assert f["_provenance"]["revenue"]["tag"] == "Revenues"
    assert abs(f["profit_margin"] - 1100 / 2800) < 1e-9     # ~0.39, not 27.5


def test_validation_summary_uses_spearman_and_applies_pregistered_gate():
    # The gate reports RANK correlation: these are fat-tailed ratios where one extreme outlier sets a
    # Pearson correlation, which is why the first gate showed trailing_pe corr=-0.015 alongside a
    # perfectly healthy 3.1% median diff.
    import pandas as pd
    good = pd.Series({"n_both_present": 400, "median_abs_pct_diff": 2.5, "spearman": 0.99,
                      "share_diff_gt_100pct": 0.01})
    bad_corr = pd.Series({"n_both_present": 400, "median_abs_pct_diff": 2.5, "spearman": 0.55,
                          "share_diff_gt_100pct": 0.01})
    bad_median = pd.Series({"n_both_present": 400, "median_abs_pct_diff": 98.0, "spearman": 0.99,
                            "share_diff_gt_100pct": 0.01})
    bad_tail = pd.Series({"n_both_present": 400, "median_abs_pct_diff": 2.5, "spearman": 0.99,
                          "share_diff_gt_100pct": 0.30})
    assert edgar._concept_passes_gate(good) is True
    assert edgar._concept_passes_gate(bad_corr) is False      # every criterion must clear, not most
    assert edgar._concept_passes_gate(bad_median) is False
    assert edgar._concept_passes_gate(bad_tail) is False


def test_cik_map_shareclass_etf_and_unmapped(tmp_path, monkeypatch):
    db = _db(tmp_path)
    fake = {"0": {"cik_str": 320193, "ticker": "AAPL"}, "1": {"cik_str": 1067983, "ticker": "BRK-B"}}
    monkeypatch.setattr(edgar, "_http_get_json", lambda url: fake)
    sector = {"AAPL": "Information Technology", "BRK-B": "Financials", "SPY": "Index", "ZZZZ": "Industrials"}
    summary = edgar.build_cik_map(["AAPL", "BRK-B", "SPY", "ZZZZ"], sector, db_path=db)
    assert storage.get_cik("AAPL", db_path=db) == "0000320193"
    assert storage.get_cik("BRK-B", db_path=db) == "0001067983"   # share-class quirk normalized to a match
    assert storage.get_cik("SPY", db_path=db) is None             # ETF excluded (no company fundamentals)
    assert "ZZZZ" in summary["unmapped"]                          # logged, never silently dropped


def test_facts_index_route_is_identical_to_sql_route(tmp_path):
    """The backfill resolves fundamentals from a pre-loaded in-memory index instead of querying per
    (ticker, date) — 266,000 queries became ~500, turning a measured 26 hours into ~15 minutes. Both
    routes carry the SAME no-lookahead gate (SQL `filed_date <= D` vs a bisect on sorted filed dates),
    and an optimization that quietly changed which facts are visible would be a lookahead leak wearing
    a performance costume. So the two must agree exactly, including on the gate boundary."""
    db = _db(tmp_path)
    storage.upsert_edgar_facts([
        _bs("StockholdersEquity", "2023-12-31", 900, filed="2024-02-01"),
        _bs("StockholdersEquity", "2024-03-31", 1000, filed="2024-05-01"),
        _bs("LongTermDebtNoncurrent", "2024-03-31", 400, filed="2024-05-01"),
        _fact("Revenues", "2023-12-31", 5000, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
        _fact("NetIncomeLoss", "2023-12-31", 500, start="2023-01-01", filed="2024-02-01", fy=2023, fp="FY"),
    ], db_path=db)
    index = edgar.build_facts_index(["T"], db_path=db)

    # includes a date BETWEEN the two filings, so the gate boundary itself is compared
    for as_of in ["2024-01-15", "2024-02-01", "2024-04-15", "2024-05-01", "2024-06-01"]:
        sql = edgar.get_fundamentals_as_of("T", as_of, price=10.0, db_path=db)
        idx = edgar.get_fundamentals_as_of("T", as_of, price=10.0, db_path=db, facts_index=index)
        assert sql.pop("_provenance") == idx.pop("_provenance"), f"provenance differs at {as_of}"
        assert sql == idx, f"resolved values differ at {as_of}"

    # and the gate genuinely bites: the 2024-05-01 filing is invisible the day before it was filed
    before = edgar.get_fundamentals_as_of("T", "2024-04-30", db_path=db, facts_index=index)
    assert before["_provenance"]["equity"]["period_end"] == "2023-12-31"
    assert before["debt_to_equity"] is None          # the debt fact did not exist yet


def test_facts_index_includes_requested_extra_tags():
    """The index is a TAG-FILTERED load. A caller needing a tag outside EDGAR_CONCEPT_TAGS (EPS, for
    SUE) otherwise receives an index containing none of its facts and computes nothing - which is how
    a SUE analysis ran to completion over 278k rows with the headline signal silently absent."""
    from src import edgar, storage
    import tempfile, os
    db = os.path.join(tempfile.mkdtemp(), "t.db")
    storage.init_db(db)
    storage.upsert_edgar_facts([
        {"cik": "C", "ticker": "T", "taxonomy": "us-gaap", "tag": "EarningsPerShareDiluted",
         "unit": "USD/shares", "period_start": "2024-01-01", "period_end": "2024-03-31",
         "fiscal_year": 2024, "fiscal_period": "Q1", "value": 1.5, "form": "10-Q",
         "accession": "a1", "filed_date": "2024-05-01", "ingested_at": "t"},
        {"cik": "C", "ticker": "T", "taxonomy": "us-gaap", "tag": "Revenues",
         "unit": "USD", "period_start": "2024-01-01", "period_end": "2024-03-31",
         "fiscal_year": 2024, "fiscal_period": "Q1", "value": 100.0, "form": "10-Q",
         "accession": "a2", "filed_date": "2024-05-01", "ingested_at": "t"},
    ], db_path=db)

    plain = edgar.build_facts_index(["T"], db_path=db)
    tags_plain = {f["tag"] for f in plain["T"][0]}
    assert "Revenues" in tags_plain
    assert "EarningsPerShareDiluted" not in tags_plain    # excluded by default - the trap

    withEPS = edgar.build_facts_index(["T"], db_path=db, extra_tags=edgar.EPS_TAGS)
    assert "EarningsPerShareDiluted" in {f["tag"] for f in withEPS["T"][0]}
