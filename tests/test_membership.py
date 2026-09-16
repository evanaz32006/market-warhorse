"""Point-in-time index membership — the survivorship measurement. Synthetic only, no network.

The universe is today's S&P 1500 projected backwards, which flatters a trend strategy by exactly
the names it omits: the ones dropped for doing badly. Measuring that needs to know who was ACTUALLY
in the index on date D, and the whole measurement is worthless if the reconstruction itself leaks
the future. Two ways it could, both tested here:

  1. Reading a snapshot from AFTER the date being reconstructed.
  2. The subtle one — S&P announces index changes about a week before they take effect, and
     Wikipedia editors add the incoming company immediately, carrying a FUTURE "Date added". A
     revision dated D legitimately lists companies that were not members on D.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import universe


def _cache(rows):
    return pd.DataFrame(rows, columns=universe.MEMBERSHIP_COLUMNS)


def _row(index_name, as_of, ticker, date_added=None, revid="1", rev_date=None):
    return {"index_name": index_name, "as_of_date": as_of, "revision_id": revid,
            "revision_date": rev_date or as_of, "ticker": ticker,
            "date_added": date_added, "sector": "Industrials"}


# ---------------------------------------------------------------------------
# No lookahead
# ---------------------------------------------------------------------------

def test_members_as_of_never_reads_a_later_snapshot():
    """The mutation this kills: taking the nearest snapshot instead of the newest EARLIER one,
    which would put a company in the index months before it joined."""
    cache = _cache([
        _row("sp500", "2024-06-01", "OLD"),
        _row("sp500", "2025-06-01", "NEW"),
    ])
    assert universe.members_as_of(cache, "sp500", "2024-06-15") == {"OLD"}
    assert universe.members_as_of(cache, "sp500", "2025-05-31") == {"OLD"}, (
        "a 2025-06 snapshot leaked into a 2025-05 read")
    assert universe.members_as_of(cache, "sp500", "2025-06-01") == {"NEW"}
    assert universe.members_as_of(cache, "sp500", "2024-01-01") == set()


def test_members_as_of_keeps_indices_separate():
    cache = _cache([_row("sp500", "2024-06-01", "BIG"), _row("sp600", "2024-06-01", "SMALL")])
    assert universe.members_as_of(cache, "sp500", "2024-07-01") == {"BIG"}
    assert universe.members_as_of(cache, "sp600", "2024-07-01") == {"SMALL"}


def test_members_as_of_on_an_empty_cache_returns_nothing_rather_than_guessing():
    assert universe.members_as_of(None, "sp500", "2024-06-01") == set()
    assert universe.members_as_of(_cache([]), "sp500", "2024-06-01") == set()


# ---------------------------------------------------------------------------
# The announcement-lookahead guard
# ---------------------------------------------------------------------------

_HTML = """
<table class="wikitable">
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>Date added</th></tr>
<tr><td>AAA</td><td>Alpha</td><td>Industrials</td><td>1990-01-02</td></tr>
<tr><td>BRK.B</td><td>Berkshire</td><td>Financials</td><td>2010-02-16</td></tr>
<tr><td>FUTURE</td><td>Announced Co</td><td>Health Care</td><td>2024-06-20</td></tr>
<tr><td>NODATE</td><td>Old Timer</td><td>Utilities</td><td>n/a</td></tr>
</table>
"""


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _patch_parse(monkeypatch, html=_HTML):
    monkeypatch.setattr(universe.requests, "get",
                        lambda *a, **k: _FakeResp({"parse": {"text": {"*": html}}}))


def test_a_company_announced_but_not_yet_effective_is_excluded(monkeypatch, capsys):
    """THE subtle leak. A revision dated 2024-06-15 lists FUTURE with Date added 2024-06-20 because
    the change was announced. Counting it as a member on 06-15 is lookahead.

    The mutation this kills: trusting the revision date alone and skipping the date_added check."""
    _patch_parse(monkeypatch)
    members = universe.constituents_at_revision(1, as_of_date="2024-06-15")
    assert "FUTURE" not in members, "a not-yet-effective member was admitted"
    assert "excluded 1 name" in capsys.readouterr().out, "the exclusion must be reported, not silent"

    later = universe.constituents_at_revision(1, as_of_date="2024-06-25")
    assert "FUTURE" in later, "once effective, the same name must be admitted"


def test_a_missing_or_unparseable_date_added_still_admits_the_row(monkeypatch):
    """Those are long-standing members. Dropping them over a formatting quirk would shrink the
    universe for a reason that has nothing to do with index membership."""
    _patch_parse(monkeypatch)
    members = universe.constituents_at_revision(1, as_of_date="2024-06-15")
    assert "NODATE" in members and members["NODATE"]["date_added"] is None


def test_share_class_symbols_are_normalized_to_our_convention(monkeypatch):
    """Wikipedia writes BRK.B, our watchlist and Yahoo use BRK-B. Without this every share-class
    name would look like a non-member and silently distort the comparison."""
    _patch_parse(monkeypatch)
    members = universe.constituents_at_revision(1, as_of_date="2024-06-15")
    assert "BRK-B" in members and "BRK.B" not in members


def test_a_revision_with_no_constituent_table_yields_nothing_rather_than_garbage(monkeypatch):
    _patch_parse(monkeypatch, html="<table><tr><th>Nav</th></tr><tr><td>x</td></tr></table>")
    assert universe.constituents_at_revision(1, as_of_date="2024-06-15") == {}


# ---------------------------------------------------------------------------
# Building the cache
# ---------------------------------------------------------------------------

def test_build_skips_pairs_already_cached_and_never_refetches(monkeypatch, tmp_path):
    """~170 requests per full build. A re-run must not re-pay for what it holds, nor overwrite it."""
    path = str(tmp_path / "membership.csv")
    _cache([_row("sp500", "2024-06-01", "AAA")]).to_csv(path, index=False)

    calls = []
    monkeypatch.setattr(universe, "revision_before",
                        lambda title, d, **k: (calls.append(d), (99, d))[1])
    monkeypatch.setattr(universe, "constituents_at_revision",
                        lambda revid, as_of_date=None, **k: {
                            "BBB": {"ticker": "BBB", "date_added": None, "sector": "X"}})

    out = universe.build_membership_history(
        ["sp500"], ["2024-06-01", "2024-07-01"], cache_path=path, sleep_sec=0)
    assert calls == ["2024-07-01"], f"refetched an already-cached date: {calls}"
    assert universe.members_as_of(out, "sp500", "2024-06-15") == {"AAA"}  # preserved, not overwritten
    assert universe.members_as_of(out, "sp500", "2024-07-15") == {"BBB"}


def test_a_failed_fetch_is_skipped_and_invents_no_members(monkeypatch, tmp_path):
    path = str(tmp_path / "m.csv")

    def _boom(title, d, **k):
        raise RuntimeError("wikipedia said no")

    monkeypatch.setattr(universe, "revision_before", _boom)
    out = universe.build_membership_history(["sp500"], ["2024-06-01"], cache_path=path, sleep_sec=0)
    assert out.empty, "a failed fetch must leave the cache empty, never fabricate constituents"
    assert not os.path.exists(path), "nothing should be written when nothing was fetched"


def test_all_members_ever_is_the_union_across_snapshots():
    """This minus today's watchlist IS the survivorship hole: names in the index while we were
    tracking that were dropped before the watchlist was built, so they were never scored once."""
    cache = _cache([
        _row("sp500", "2024-06-01", "SURVIVOR"), _row("sp500", "2024-06-01", "DELISTED"),
        _row("sp500", "2025-06-01", "SURVIVOR"), _row("sp500", "2025-06-01", "NEWCOMER"),
    ])
    assert universe.all_members_ever(cache) == {"SURVIVOR", "DELISTED", "NEWCOMER"}
    assert universe.all_members_ever(cache, ["sp600"]) == set()


# ---------------------------------------------------------------------------
# The survivorship summary built on top of membership
# ---------------------------------------------------------------------------

def test_survivorship_hole_counts_only_names_absent_from_the_watchlist(tmp_path):
    """The hole is names that were in the index during the window and are NOT in the universe we
    score — those were never scored once, so no backtest could have contained them."""
    from src import research
    cache = _cache([
        _row("sp500", "2024-06-01", "KEPT"), _row("sp500", "2024-06-01", "DROPPED"),
        _row("sp500", "2025-06-01", "KEPT"), _row("sp500", "2025-06-01", "ADDED"),
    ])
    wl = tmp_path / "watchlist.csv"
    pd.DataFrame({"ticker": ["KEPT", "ADDED", "UNRELATED"]}).to_csv(wl, index=False)

    summary, missing = research.survivorship_hole(cache=cache, watchlist_path=str(wl))
    row = summary[summary["index_name"] == "sp500"].iloc[0]
    assert row["ever_members"] == 3 and row["tracked"] == 2 and row["missing"] == 1
    assert missing["sp500"] == ["DROPPED"]
    assert row["missing_pct"] == pytest.approx(33.3, abs=0.1)
    assert row["snapshots"] == 2


def test_survivorship_hole_on_an_empty_cache_reports_nothing_rather_than_zero(tmp_path):
    """No membership history means the question is UNANSWERED, which is different from answering
    'no bias'. The mutation this kills: returning a zero-hole summary when the cache is missing."""
    from src import research
    wl = tmp_path / "watchlist.csv"
    pd.DataFrame({"ticker": ["A"]}).to_csv(wl, index=False)
    summary, missing = research.survivorship_hole(cache=_cache([]), watchlist_path=str(wl))
    assert summary.empty and missing == {}
