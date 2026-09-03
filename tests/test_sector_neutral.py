"""v0.3 proof tests: sector-neutral value/quality ranking.

Covers the spec's required cases: within-sector ranking correctness, the small-sector
cross-sectional fallback (+ flag), benchmark-ETF exclusion, and label normalization. The
regression guarantee (short interest + all price/volume percentiles stay cross-sectional; the
62 existing tests stay green because the new params default off) is enforced by leaving
scoring.compute_percentiles's new args unset in every other test file.
"""

import pytest

import app
from src import scoring
from src.config import SECTOR_NEUTRAL_COMPOSITES


_VALUE_FIELDS = {"trailing_pe", "price_to_sales", "ev_to_ebitda", "price_to_book"}


def _value_row(pe):
    """A fundamentals dict whose value ratios all scale with `pe` (cheaper = lower = better)."""
    return {"trailing_pe": pe, "price_to_sales": pe / 5.0, "ev_to_ebitda": pe / 2.0, "price_to_book": pe / 8.0}


def _pool(tech_pes, bank_pes, small_pes=None, etfs=None):
    """Build features + sector map for a mixed universe. tech expensive, banks cheap."""
    fbt, sec = {}, {}
    for i, pe in enumerate(tech_pes):
        t = f"T{i}"; fbt[t] = _value_row(pe); sec[t] = "Information Technology"
    for i, pe in enumerate(bank_pes):
        t = f"B{i}"; fbt[t] = _value_row(pe); sec[t] = "Financials"
    for i, pe in enumerate(small_pes or []):
        t = f"E{i}"; fbt[t] = _value_row(pe); sec[t] = "Energy"
    for t, pe in (etfs or {}).items():
        fbt[t] = _value_row(pe); sec[t] = "Index"
    return fbt, sec


def _sn(fbt, sec, exclude=(), min_size=8):
    return scoring.compute_percentiles(
        fbt, sector_by_ticker=sec,
        sector_neutral_composites={"value_percentile", "quality_percentile"},
        exclude_tickers=set(exclude), min_sector_size=min_size,
    )


# ---------------------------------------------------------------------------
# Within-sector correctness
# ---------------------------------------------------------------------------

def test_cheapest_in_sector_ranks_high_even_if_expensive_vs_universe():
    # T0 (pe=25) is the cheapest of 8 tech names but pricier than every bank (pe 5-12).
    tech = [25, 30, 35, 40, 45, 50, 55, 60]
    banks = [5, 6, 7, 8, 9, 10, 11, 12]
    fbt, sec = _pool(tech, banks)

    xs = scoring.compute_percentiles(fbt)              # cross-sectional (v0.2 style)
    sn = _sn(fbt, sec)                                  # sector-neutral (v0.3)

    # cross-sectionally T0 looks mid/low (banks are cheaper); within tech it's the top.
    assert xs["T0"]["value_percentile"] < 60
    assert sn["T0"]["value_percentile"] == pytest.approx(100.0)
    # the priciest tech name bottoms its own sector regardless of the cheap banks
    assert sn["T7"]["value_percentile"] == pytest.approx(12.5, abs=0.1)


def test_within_sector_ranking_is_independent_of_the_other_sector():
    # Two identical tech universes, one paired with cheap banks, one with expensive banks:
    # the tech value ranks must be IDENTICAL (sector-neutral => other sectors don't matter).
    tech = [25, 35, 45, 55, 20, 30, 40, 50]
    a = _sn(*_pool(tech, [5, 6, 7, 8, 9, 10, 11, 12]))
    b = _sn(*_pool(tech, [90, 91, 92, 93, 94, 95, 96, 97]))
    for i in range(len(tech)):
        assert a[f"T{i}"]["value_percentile"] == pytest.approx(b[f"T{i}"]["value_percentile"])


# ---------------------------------------------------------------------------
# Small-sector fallback
# ---------------------------------------------------------------------------

def test_small_sector_falls_back_to_cross_sectional_and_flags():
    tech = [25, 30, 35, 40, 45, 50, 55, 60]          # 8 -> big enough
    banks = [5, 6, 7, 8, 9, 10, 11, 12]              # 8 -> big enough
    energy = [20, 22, 24]                             # 3 -> too small, must fall back
    fbt, sec = _pool(tech, banks, small_pes=energy)
    sn = _sn(fbt, sec)

    # energy names flagged and given a (non-None) cross-sectional value
    for i in range(3):
        assert sn[f"E{i}"]["sector_rank_fallback"] is True
        assert sn[f"E{i}"]["value_percentile"] is not None
    # big-sector members are NOT flagged
    assert sn["T0"]["sector_rank_fallback"] is False
    assert sn["B0"]["sector_rank_fallback"] is False

    # the fallback value equals a cross-sectional rank over the non-excluded pool (E0 pe=20 is
    # cheaper than all tech but pricier than all banks -> mid-pack across the 19 names)
    xs_over_pool = scoring.compute_percentiles(fbt)  # no exclusions here, same pool
    assert sn["E0"]["value_percentile"] == pytest.approx(xs_over_pool["E0"]["value_percentile"], abs=0.1)


def test_exactly_at_threshold_is_within_sector_not_fallback():
    # A sector with exactly min_size (8) present members ranks within-sector (>=, not >).
    tech = [10, 20, 30, 40, 50, 60, 70, 80]
    banks = [5, 6, 7, 8, 9, 10, 11, 12]
    fbt, sec = _pool(tech, banks)
    sn = _sn(fbt, sec, min_size=8)
    assert all(sn[f"T{i}"]["sector_rank_fallback"] is False for i in range(8))
    assert sn["T0"]["value_percentile"] == pytest.approx(100.0)  # cheapest tech tops its sector


# ---------------------------------------------------------------------------
# ETF exclusion
# ---------------------------------------------------------------------------

def test_benchmark_etf_is_excluded_from_value_and_quality():
    tech = [25, 30, 35, 40, 45, 50, 55, 60]
    banks = [5, 6, 7, 8, 9, 10, 11, 12]
    fbt, sec = _pool(tech, banks, etfs={"XLK": 28, "XLF": 9})
    sn = _sn(fbt, sec, exclude={"XLK", "XLF"})

    for etf in ("XLK", "XLF"):
        assert sn[etf]["value_percentile"] is None
        assert sn[etf]["quality_percentile"] is None
        assert sn[etf]["sector_rank_fallback"] is False   # excluded, not a fallback

    # excluding the ETFs must not change the real stocks' within-sector ranks
    sn_no_etf = _sn(*_pool(tech, banks))
    assert sn["T0"]["value_percentile"] == pytest.approx(sn_no_etf["T0"]["value_percentile"])


def test_excluded_etf_does_not_count_toward_sector_size():
    # A sector of 7 real names + 1 ETF has only 7 non-excluded members -> falls back.
    fbt, sec = {}, {}
    for i, pe in enumerate([10, 20, 30, 40, 50, 60, 70]):   # 7 real energy names
        t = f"E{i}"; fbt[t] = _value_row(pe); sec[t] = "Energy"
    fbt["XLE"] = _value_row(35); sec["XLE"] = "Energy"       # ETF mislabeled into the sector
    # add a big sector so a cross-sectional pool exists
    for i, pe in enumerate([5, 6, 7, 8, 9, 11, 12, 13]):
        t = f"B{i}"; fbt[t] = _value_row(pe); sec[t] = "Financials"
    sn = _sn(fbt, sec, exclude={"XLE"}, min_size=8)
    assert sn["XLE"]["value_percentile"] is None
    assert all(sn[f"E{i}"]["sector_rank_fallback"] is True for i in range(7))  # only 7 real -> fallback


# ---------------------------------------------------------------------------
# Normalization (app-level helper)
# ---------------------------------------------------------------------------

def test_normalize_sector_maps_fragments_to_gics():
    assert app._normalize_sector("Healthcare") == "Health Care"
    assert app._normalize_sector("Tech-Software") == "Information Technology"
    assert app._normalize_sector("Utilities-Power") == "Utilities"
    assert app._normalize_sector("Industrials-Power") == "Industrials"
    # already-GICS and distinct sub-groups pass through unchanged
    assert app._normalize_sector("Health Care") == "Health Care"
    assert app._normalize_sector("Semiconductors") == "Semiconductors"
    assert app._normalize_sector("Index") == "Index"


def test_normalized_healthcare_fragment_joins_its_gics_peers():
    # 5 "Healthcare" names + 3 "Health Care" names. Un-normalized: two groups of 5 and 3, both
    # < 8 -> all fall back. Normalized to one "Health Care" group of 8 -> ranks within-sector.
    raw = {f"H{i}": _value_row(pe) for i, pe in enumerate([10, 20, 30, 40, 50])}   # "Healthcare"
    raw.update({f"G{i}": _value_row(pe) for i, pe in enumerate([15, 25, 35])})     # "Health Care"
    sec = {t: app._normalize_sector("Healthcare") for t in [f"H{i}" for i in range(5)]}
    sec.update({t: app._normalize_sector("Health Care") for t in [f"G{i}" for i in range(3)]})
    assert len(set(sec.values())) == 1                       # normalization merged them
    sn = _sn(raw, sec, min_size=8)
    assert all(sn[t]["sector_rank_fallback"] is False for t in raw)   # one group of 8 -> within-sector
    assert sn["H0"]["value_percentile"] == pytest.approx(100.0)       # cheapest (pe=10) tops the merged sector


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------

def test_v03_config_targets_value_and_quality_only():
    assert SECTOR_NEUTRAL_COMPOSITES == {"value_percentile", "quality_percentile"}
    # short_interest_percentile must NOT be sector-neutralized this version
    assert "short_interest_percentile" not in SECTOR_NEUTRAL_COMPOSITES
