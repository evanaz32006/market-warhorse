"""Database backup — synthetic databases only.

An unverified backup is a guess. A truncated write, a full disk or a failing drive all produce a
file that LOOKS like a backup — right name, plausible size — and reveals itself only on the day it
is needed. These tests exist to make sure the failure is loud at backup time instead.
"""
import os
import sqlite3

import pytest

from src import backup, storage


def _seed(path, n_prices=25):
    storage.init_db(path)
    rows = [{"ticker": "AAA", "date": "2024-%02d-%02d" % (1 + i // 28, 1 + i % 28),
             "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0,
             "timestamp_fetched": "2026-09-10T00:00:00Z"}
            for i in range(n_prices)]
    storage.upsert_price_rows(rows, db_path=path)
    return path


def test_backup_is_a_faithful_verified_copy(tmp_path):
    src = _seed(str(tmp_path / "src.db"))
    dest = str(tmp_path / "backups")
    summary = backup.backup_database(dest, db_path=src)

    assert summary["verified"] is True
    assert summary["integrity"] == "ok"
    assert summary["counts_match"] is True
    assert os.path.exists(summary["target"])
    assert summary["source_counts"]["price_history"] == 25
    assert summary["backup_counts"]["price_history"] == 25


def test_backup_survives_wal_mode_unlike_a_plain_file_copy(tmp_path):
    """The reason `VACUUM INTO` is used instead of `shutil.copy`.

    In WAL mode, committed pages live in the `-wal` sidecar until a checkpoint. Copying only the
    main database file silently loses recent writes — a backup that restores cleanly and is missing
    yesterday's data. This writes rows, does NOT checkpoint, and asserts the backup has them."""
    src = _seed(str(tmp_path / "wal.db"), n_prices=5)
    conn = storage._connect(src)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    conn.close()

    storage.upsert_price_rows(
        [{"ticker": "BBB", "date": "2025-01-%02d" % (i + 1), "open": 1.0, "high": 1.0,
          "low": 1.0, "close": 1.0, "volume": 1.0,
          "timestamp_fetched": "2026-09-10T00:00:00Z"} for i in range(7)], db_path=src)

    summary = backup.backup_database(str(tmp_path / "b"), db_path=src)
    conn = sqlite3.connect(summary["target"])
    try:
        n = conn.execute("SELECT COUNT(*) FROM price_history WHERE ticker='BBB'").fetchone()[0]
    finally:
        conn.close()
    assert n == 7, "uncheckpointed WAL writes were lost — this is the plain-copy failure mode"


def test_a_timestamped_name_cannot_overwrite_a_previous_backup(tmp_path):
    """The failure mode of a fixed filename is destroying last week's GOOD backup with today's bad
    one. Two backups in a row must produce two files."""
    src = _seed(str(tmp_path / "s.db"))
    dest = str(tmp_path / "b")
    a = backup.backup_database(dest, db_path=src)
    b = backup.backup_database(dest, db_path=src)
    assert a["target"] != b["target"]
    assert len([f for f in os.listdir(dest) if f.endswith(".db")]) == 2


def test_a_corrupted_backup_raises_instead_of_reporting_success(tmp_path, monkeypatch):
    """THE test that makes this a backup rather than a copy.

    A backup that reports failure in a field nobody reads is worse than no backup, because it
    produces false confidence. Verification failure must raise."""
    src = _seed(str(tmp_path / "s.db"))
    real_counts = backup._table_counts

    def lying_counts(db_path, tables=backup.VERIFY_TABLES):
        out = real_counts(db_path, tables)
        if "backups" in db_path or os.path.basename(db_path).startswith("market"):
            pass
        # Simulate a short write: the backup appears to hold fewer rows than the source.
        if db_path != src:
            out["price_history"] = 3
        return out

    monkeypatch.setattr(backup, "_table_counts", lying_counts)
    with pytest.raises(RuntimeError, match="BACKUP FAILED VERIFICATION"):
        backup.backup_database(str(tmp_path / "b"), db_path=src)


def test_a_missing_source_is_a_hard_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup.backup_database(str(tmp_path / "b"), db_path=str(tmp_path / "nope.db"))


def test_default_path_is_timestamped_and_keeps_the_database_name(tmp_path):
    from datetime import datetime, timezone
    when = datetime(2026, 9, 10, 15, 4, 5, tzinfo=timezone.utc)
    p = backup.default_backup_path(str(tmp_path), db_path="/x/market_data.db", now=when)
    assert os.path.basename(p) == "market_data_20260910T150405Z.db"


# ---------------------------------------------------------------------------
# A moving source is not a corrupt backup (found 2026-09-17)
# ---------------------------------------------------------------------------

def _seed_counts(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS feature_snapshots (id INTEGER PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO price_history (id) VALUES (?)", [(i,) for i in range(rows)])
    conn.executemany("INSERT INTO feature_snapshots (id) VALUES (?)", [(i,) for i in range(rows)])
    conn.commit()
    conn.close()


def test_a_source_written_to_during_the_copy_is_inconclusive_not_corrupt(tmp_path, monkeypatch):
    """THE DISTINCTION THIS ENCODES. VACUUM INTO snapshots the source when its read transaction
    opens; verifying against the source AFTERWARDS compares the copy to a database that has moved
    on. A real 13.9 GB backup was rejected on 2026-09-17 for exactly this - feature_snapshots grew
    103,225 rows during the 700s copy while every static table matched to the row.

    Both cases must still RAISE - a backup nobody can verify is not a verified backup - but the
    operator has to be told which problem they have, because the remedies are opposite: re-run when
    idle, versus the destination is broken.

    The mutation this kills: treating any count difference as corruption."""
    src = str(tmp_path / "src.db")
    _seed_counts(src, 10)

    real_counts = backup._table_counts
    calls = {"n": 0}

    def growing_counts(path, *a, **k):
        # First call is the "before" reading; the second is "after", by which point a concurrent
        # writer has appended. The BACKUP file itself is untouched and keeps the original count.
        out = dict(real_counts(path, *a, **k))
        if path == src:
            calls["n"] += 1
            if calls["n"] >= 2:
                out["feature_snapshots"] = out.get("feature_snapshots", 0) + 5
        return out

    monkeypatch.setattr(backup, "_table_counts", growing_counts)
    with pytest.raises(RuntimeError) as e:
        backup.backup_database(str(tmp_path / "dest"), db_path=src)
    msg = str(e.value)
    assert "NOT VERIFIED" in msg
    assert "SOURCE changed while the copy ran" in msg
    assert "no writer active" in msg, "the operator must be told the remedy"
    assert "must not be trusted" not in msg, (
        "a moving source is not evidence of corruption and must not be reported as such")


def test_a_genuinely_short_copy_is_still_reported_as_corrupt(tmp_path, monkeypatch):
    """The strict path must survive the new branch: when the source did NOT move, any count
    difference is a real failure and keeps the original hard wording."""
    src = str(tmp_path / "src.db")
    _seed_counts(src, 10)

    real_counts = backup._table_counts

    def short_backup_counts(path, *a, **k):
        out = dict(real_counts(path, *a, **k))
        if path != src:                      # the BACKUP is missing rows; source is stable
            out["price_history"] = max(0, out.get("price_history", 0) - 3)
        return out

    monkeypatch.setattr(backup, "_table_counts", short_backup_counts)
    with pytest.raises(RuntimeError) as e:
        backup.backup_database(str(tmp_path / "dest"), db_path=src)
    assert "must not be trusted" in str(e.value)
    assert "NOT VERIFIED" not in str(e.value)
