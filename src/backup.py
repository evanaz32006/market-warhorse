"""Database backup — and verification, which is the part that makes it a backup rather than a copy.

## Why this is not optional

`data/market_data.db` is **partially irreplaceable**. `PARAMS["fetch_period"]` is 2 years, so
yfinance will no longer serve bars from before roughly two years ago, while the cache holds history
from 2024-06-24. Every bar older than the rolling two-year window exists in exactly one place: this
file. Losing it permanently destroys that window, and with it the ability to reproduce v0.1-v0.5's
backfills. The 33.9M EDGAR facts and 480k insider rows are refetchable but would take hours.

## Why `VACUUM INTO` rather than copying the file

A plain file copy of a live SQLite database in WAL mode is a **corrupt** backup: the `-wal` sidecar
holds committed pages that are not yet in the main file, so copying only the main file silently
loses recent writes, and copying both while a write is in flight can tear a transaction. `VACUUM
INTO` asks SQLite itself for a consistent, fully-checkpointed, defragmented snapshot, taken safely
while readers and writers continue.

## Why the verification step exists

An unverified backup is a guess. A truncated write, a full disk, or a bad drive all produce a file
that LOOKS like a backup — right name, plausible size — and fails only on the day it is needed. So
every backup is reopened, integrity-checked, and row-counted against the source before it is
reported as successful.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone

from src import storage

# Tables whose row counts are compared source-vs-backup. Not every table — the point is a fast,
# meaningful check on the ones that carry irreplaceable or expensive data.
VERIFY_TABLES = ["price_history", "edgar_facts", "feature_snapshots", "insider_transactions"]


def _table_counts(db_path, tables=VERIFY_TABLES):
    conn = sqlite3.connect(db_path)
    try:
        out = {}
        for t in tables:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
            out[t] = conn.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] if row else None
        return out
    finally:
        conn.close()


def default_backup_path(dest_dir, db_path=None, now=None):
    """A timestamped name, so a backup can never silently overwrite the previous one.

    `VACUUM INTO` refuses to write to an existing file, which is a feature: the failure mode of a
    fixed filename is destroying last week's good backup with today's broken one."""
    db_path = db_path or storage.DEFAULT_DB_PATH
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.splitext(os.path.basename(db_path))[0]
    path = os.path.join(dest_dir, "%s_%s.db" % (base, stamp))
    # Second-resolution stamps collide when two backups run in the same second, and `VACUUM INTO`
    # then fails with an opaque SQLite error rather than doing something sensible. Uniquify instead
    # — this preserves the never-overwrite guarantee without turning a harmless re-run into a
    # confusing failure.
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(dest_dir, "%s_%s-%d.db" % (base, stamp, suffix))
        suffix += 1
    return path


def backup_database(dest_dir, db_path=None, verify=True):
    """Write a verified, consistent snapshot to `dest_dir`. Returns a summary dict.

    Raises rather than returning a failure flag: a backup that reports failure in a field nobody
    reads is worse than no backup, because it produces false confidence."""
    db_path = db_path or storage.DEFAULT_DB_PATH
    if not os.path.exists(db_path):
        raise FileNotFoundError("no database at %s" % db_path)
    os.makedirs(dest_dir, exist_ok=True)
    target = default_backup_path(dest_dir, db_path=db_path)

    source_bytes = os.path.getsize(db_path)
    free = getattr(os, "statvfs", None)
    if hasattr(os, "statvfs"):                       # POSIX only; Windows falls through
        st = os.statvfs(dest_dir)
        free_bytes = st.f_bavail * st.f_frsize
        if free_bytes < source_bytes:
            raise OSError("destination has %.1f GB free but the database is %.1f GB"
                          % (free_bytes / 1e9, source_bytes / 1e9))

    started = time.time()
    # Counts BEFORE the copy as well as after. VACUUM INTO snapshots the source at the moment its
    # read transaction opens, so verifying against the source AFTERWARDS compares the copy to a
    # database that may have moved on. Without a "before" reading the two failure modes are
    # indistinguishable: a genuinely incomplete copy, and a perfectly good copy of a source that
    # was being written to. Learned the hard way on 2026-09-17 - a 13.9 GB backup taken while the
    # v0.6 backfill was running was rejected because feature_snapshots had grown 103,225 rows
    # during the 700s copy, while every static table matched to the row.
    counts_before = _table_counts(db_path) if verify else None
    print("[backup] %s (%.1f GB) -> %s" % (db_path, source_bytes / 1e9, target))
    conn = sqlite3.connect(db_path, timeout=120)
    try:
        # Parameter binding is not permitted for VACUUM INTO's target, so the path is quoted the way
        # SQLite expects (doubled single quotes). It is an operator-supplied local path, never
        # untrusted input.
        conn.execute("VACUUM INTO '%s'" % target.replace("'", "''"))
    finally:
        conn.close()
    elapsed = time.time() - started
    backup_bytes = os.path.getsize(target)

    summary = {
        "source": db_path, "target": target,
        "source_bytes": source_bytes, "backup_bytes": backup_bytes,
        "elapsed_sec": round(elapsed, 1),
        "verified": False, "integrity": None, "counts_match": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    print("[backup] wrote %.1f GB in %.0fs (VACUUM compacts, so smaller than the source is normal)"
          % (backup_bytes / 1e9, elapsed))

    if verify:
        conn = sqlite3.connect(target)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        summary["integrity"] = integrity
        source_counts = _table_counts(db_path)
        backup_counts = _table_counts(target)
        summary["source_counts"] = source_counts
        summary["source_counts_before"] = counts_before
        summary["backup_counts"] = backup_counts

        # A table the WRITER touched during the copy cannot be verified by this method at all: the
        # copy is a snapshot of one instant and the source is a different instant. Separated from a
        # real mismatch so the operator is told which problem they have.
        moved = {t: (counts_before[t], source_counts[t])
                 for t in source_counts if counts_before[t] != source_counts[t]}
        mismatches, inconclusive = {}, {}
        for t in source_counts:
            if source_counts[t] == backup_counts[t]:
                continue
            lo, hi = sorted((counts_before[t], source_counts[t]))
            if t in moved and lo <= backup_counts[t] <= hi:
                inconclusive[t] = (counts_before[t], backup_counts[t], source_counts[t])
            else:
                mismatches[t] = (source_counts[t], backup_counts[t])
        summary["counts_match"] = not mismatches and not inconclusive
        summary["source_moved_during_copy"] = moved
        summary["inconclusive_tables"] = inconclusive
        summary["verified"] = (integrity == "ok") and not mismatches and not inconclusive
        for t in VERIFY_TABLES:
            state = ("OK" if source_counts[t] == backup_counts[t]
                     else "INCONCLUSIVE (source was being written)" if t in inconclusive
                     else "MISMATCH")
            print("[backup]   %-20s source %-12s backup %-12s %s"
                  % (t, source_counts[t], backup_counts[t], state))
        if mismatches:
            raise RuntimeError(
                "BACKUP FAILED VERIFICATION — integrity=%s mismatches=%s. The file at %s must not "
                "be trusted." % (integrity, mismatches, target))
        if inconclusive:
            raise RuntimeError(
                "BACKUP NOT VERIFIED — the SOURCE changed while the copy ran, so this check cannot "
                "prove anything about %s. Every other table matched exactly and integrity=%s, so "
                "the file is probably a good snapshot of an earlier instant, but it has NOT been "
                "verified and must not be relied on as one. Re-run with no writer active "
                "(no backfill, no nightly run). Tables that moved: %s. File: %s"
                % (sorted(inconclusive), integrity, moved, target))
        print("[backup] verified: integrity ok, all row counts match")
    return summary
