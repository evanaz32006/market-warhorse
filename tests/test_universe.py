"""Proof tests for the S&P 500 universe expansion: sector->benchmark mapping rules,
preservation of hand-assigned watchlist rows during the merge, idempotency of repeated
merges, and the never-invent-data fallback when the network source is unreachable.
"""

import pandas as pd
import pytest

from src import universe


def test_assign_benchmark_semiconductor_overrides_it_default():
    sector, benchmark = universe.assign_benchmark("Information Technology", "Semiconductors")
    assert sector == "Semiconductors"
    assert benchmark == "SMH"

    sector, benchmark = universe.assign_benchmark("Information Technology", "Semiconductor Materials & Equipment")
    assert benchmark == "SMH"


def test_assign_benchmark_plain_it_maps_to_qqq():
    sector, benchmark = universe.assign_benchmark("Information Technology", "Software")
    assert sector == "Information Technology"
    assert benchmark == "QQQ"


def test_assign_benchmark_mapped_sector():
    sector, benchmark = universe.assign_benchmark("Energy", "Oil & Gas Exploration & Production")
    assert benchmark == "XLE"


def test_assign_benchmark_unmapped_sector_defaults_to_spy():
    sector, benchmark = universe.assign_benchmark("Some New Sector", "Whatever")
    assert sector == "Some New Sector"
    assert benchmark == "SPY"


def _existing_watchlist():
    return pd.DataFrame([
        {"ticker": "AVGO", "sector": "Semiconductors", "benchmark": "SMH", "notes": "core"},
        {"ticker": "SPY", "sector": "Index", "benchmark": "SPY", "notes": "benchmark"},
    ])


def test_build_universe_watchlist_preserves_existing_hand_assigned_row():
    sp500_df = pd.DataFrame([
        {"Symbol": "AVGO", "GICS Sector": "Information Technology", "GICS Sub-Industry": "Semiconductors"},
        {"Symbol": "MMM", "GICS Sector": "Industrials", "GICS Sub-Industry": "Industrial Conglomerates"},
    ])
    merged = universe.build_universe_watchlist(_existing_watchlist(), sp500_df)

    avgo_row = merged[merged["ticker"] == "AVGO"].iloc[0]
    assert avgo_row["benchmark"] == "SMH"
    assert avgo_row["notes"] == "core"

    mmm_row = merged[merged["ticker"] == "MMM"].iloc[0]
    assert mmm_row["benchmark"] == "XLI"
    assert mmm_row["notes"] == "sp500_auto"


def test_build_universe_watchlist_adds_missing_benchmark_etf_rows():
    sp500_df = pd.DataFrame([
        {"Symbol": "HD", "GICS Sector": "Consumer Discretionary", "GICS Sub-Industry": "Home Improvement Retail"},
    ])
    merged = universe.build_universe_watchlist(_existing_watchlist(), sp500_df)

    xly_row = merged[merged["ticker"] == "XLY"].iloc[0]
    assert xly_row["sector"] == "Index"
    assert xly_row["benchmark"] == "SPY"
    assert xly_row["notes"] == "benchmark"


def test_build_universe_watchlist_normalizes_dot_tickers_to_yfinance_dash_convention():
    sp500_df = pd.DataFrame([
        {"Symbol": "BRK.B", "GICS Sector": "Financials", "GICS Sub-Industry": "Multi-Sector Holdings"},
    ])
    merged = universe.build_universe_watchlist(_existing_watchlist(), sp500_df)
    assert "BRK.B" not in set(merged["ticker"])
    assert "BRK-B" in set(merged["ticker"])


def test_build_universe_watchlist_is_idempotent():
    sp500_df = pd.DataFrame([
        {"Symbol": "MMM", "GICS Sector": "Industrials", "GICS Sub-Industry": "Industrial Conglomerates"},
    ])
    once = universe.build_universe_watchlist(_existing_watchlist(), sp500_df)
    twice = universe.build_universe_watchlist(once, sp500_df)
    assert len(twice) == len(once)


def test_fetch_sp500_constituents_falls_back_to_cache_on_network_failure(tmp_path, monkeypatch):
    cache_path = tmp_path / "sp500_constituents.csv"
    cache_path.write_text("Symbol,GICS Sector,GICS Sub-Industry\nNVDA,Information Technology,Semiconductors\n")

    def _raise(*args, **kwargs):
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(universe.requests, "get", _raise)
    df = universe.fetch_sp500_constituents(cache_path=str(cache_path))
    assert list(df["Symbol"]) == ["NVDA"]


def test_fetch_sp500_constituents_returns_empty_when_no_cache_and_no_network(tmp_path, monkeypatch):
    cache_path = tmp_path / "does_not_exist.csv"

    def _raise(*args, **kwargs):
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(universe.requests, "get", _raise)
    df = universe.fetch_sp500_constituents(cache_path=str(cache_path))
    assert df.empty


# ---------------------------------------------------------------------------
# v0.5 universe expansion
# ---------------------------------------------------------------------------

def test_index_fetch_falls_back_to_cache_and_never_invents_constituents(tmp_path, monkeypatch):
    """live -> cache -> EMPTY. The one thing a universe builder must never do is make up members,
    so a total failure yields zero new tickers rather than a guess (CLAUDE.md invariant #2)."""
    import pandas as pd
    from src import universe
    cache = tmp_path / "cached.csv"
    pd.DataFrame({"Symbol": ["AAA"], "GICS Sector": ["Industrials"],
                  "GICS Sub-Industry": ["Building Products"]}).to_csv(cache, index=False)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(universe.requests, "get", boom)
    df = universe.fetch_index_constituents("sp400", cache_path=str(cache))
    assert list(df["Symbol"]) == ["AAA"]          # served from cache
    assert df["size_bucket"].iloc[0] == "mid"

    missing = tmp_path / "nope.csv"
    empty = universe.fetch_index_constituents("sp400", cache_path=str(missing))
    assert empty.empty                            # no cache either -> nothing, never invented


def test_index_cache_stores_the_parsed_frame_not_the_raw_body(tmp_path, monkeypatch):
    """The original code wrote the response body BEFORE parsing it, so any 200-with-garbage response
    (captive portal, an error page served with a 200, an HTML redirect) permanently poisoned the
    cache with something that would never parse again. Writing only after a successful parse means
    the cache always holds usable data."""
    from src import universe

    class Resp:
        status_code = 200
        text = "<html><body>not a constituent table at all</body></html>"
        def raise_for_status(self): pass

    cache = tmp_path / "c.csv"
    monkeypatch.setattr(universe.requests, "get", lambda *a, **k: Resp())
    df = universe.fetch_index_constituents("sp400", cache_path=str(cache))
    assert df.empty                                # unparseable -> treated as a failure
    assert not cache.exists(), "garbage response was written to the cache"


def test_size_bucket_drives_the_benchmark_but_not_the_sector_label():
    """Mid/small caps get a SIZE benchmark because no liquid mid/small SECTOR ETF family exists.
    The sector LABEL must survive regardless, because v0.3 sector-neutral ranking depends on it -
    losing it would silently drop small caps out of within-sector ranking."""
    from src import universe
    for bucket, expected in [("large", "XLI"), ("mid", "IJH"), ("small", "IJR")]:
        sector, bench = universe.assign_benchmark("Industrials", "Building Products", bucket)
        assert bench == expected
        assert sector == "Industrials", "sector label lost - sector-neutral ranking would break"
    # the semiconductor override still labels correctly even when size-benchmarked
    sector, bench = universe.assign_benchmark("Information Technology", "Semiconductors", "small")
    assert sector == "Semiconductors" and bench == "IJR"


def test_watchlist_merge_backfills_size_bucket_and_keeps_existing_rows(tmp_path):
    """Everything in the watchlist before v0.5 came from the S&P 500, so backfilling those rows as
    'large' is a statement of fact, not a default. Hand-assigned rows stay untouched."""
    import pandas as pd
    from src import universe
    existing = pd.DataFrame([{"ticker": "NVDA", "sector": "Semiconductors", "benchmark": "SMH",
                              "notes": "core"}])
    new = pd.DataFrame([{"Symbol": "AAON", "GICS Sector": "Industrials",
                         "GICS Sub-Industry": "Building Products", "size_bucket": "mid",
                         "source_index": "sp400"}])
    merged = universe.build_universe_watchlist(existing, new)
    nvda = merged[merged.ticker == "NVDA"].iloc[0]
    assert nvda["notes"] == "core" and nvda["benchmark"] == "SMH"   # untouched
    assert nvda["size_bucket"] == "large"                           # backfilled as fact
    aaon = merged[merged.ticker == "AAON"].iloc[0]
    assert aaon["benchmark"] == "IJH" and aaon["size_bucket"] == "mid"
    assert aaon["notes"] == "sp400_auto"                            # index-named provenance
    # idempotent
    assert len(universe.build_universe_watchlist(merged, new)) == len(merged)


def test_dollar_volume_flags_illiquid_without_dropping_and_short_history_is_unknown():
    """A name that trades $200k/day cannot absorb a real order, so a backtest that fills in it is
    fiction. Measured and FLAGGED - the row is still scored and stored; only the portfolio
    simulation excludes it. And with too little history the flag is None (unknown), never 0
    (liquid): absence of evidence is not evidence of liquidity."""
    import pandas as pd
    from src import features
    from src.config import PARAMS

    def _hist(close, vol, n=30):
        return pd.DataFrame({"date": [f"2025-01-{i+1:02d}" for i in range(n)],
                             "open": [close] * n, "high": [close] * n, "low": [close] * n,
                             "close": [close] * n, "volume": [vol] * n})

    liquid = features._volume_features(_hist(100.0, 1_000_000), PARAMS)
    assert liquid["dollar_volume_20d"] == pytest.approx(100e6)
    assert liquid["illiquid_flag"] == 0

    thin = features._volume_features(_hist(5.0, 20_000), PARAMS)      # $100k/day
    assert thin["illiquid_flag"] == 1
    assert thin["dollar_volume_20d"] is not None                      # measured, not dropped

    short = features._volume_features(_hist(100.0, 1_000_000, n=5), PARAMS)
    assert short["dollar_volume_20d"] is None
    assert short["illiquid_flag"] is None, "unknown liquidity must not read as liquid"
