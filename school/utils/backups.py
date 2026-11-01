"""Consistent, integrity-checked SQLite backup and restore helpers.

A live SQLite file must not be copied with a plain file copy: an in-flight
write, a pending WAL file or an open handle can produce a torn backup. These
helpers use SQLite's online backup API, verify every copy with
``PRAGMA integrity_check`` and swap files atomically on restore.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


# A backup of this application always contains the migration table. Requiring
# it stops an unrelated SQLite file from being uploaded or restored by mistake.
REQUIRED_TABLES = ("django_migrations",)


class BackupError(RuntimeError):
    """Raised when a backup cannot be created, verified or restored."""


def timestamped_name(prefix="backup", suffix=".sqlite3"):
    """Return a sortable, second-resolution backup filename."""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"


def verify_backup(path, required_tables=REQUIRED_TABLES):
    """Run SQLite's own integrity check against a backup file.

    Returns ``(ok, message)`` instead of raising so callers can show the
    reason in the UI or a JSON error body.
    """
    backup = Path(path)
    if not backup.is_file():
        return False, "Backup file not found."
    if backup.stat().st_size == 0:
        return False, "Backup file is empty."

    try:
        with closing(sqlite3.connect(str(backup))) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                detail = row[0] if row else "no result returned"
                return False, f"SQLite integrity check failed: {detail}"

            for table in required_tables:
                found = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if not found:
                    return False, f"Backup is missing the '{table}' table."
    except (sqlite3.Error, OSError) as exc:
        return False, f"Backup is not a readable SQLite database: {exc}"

    return True, "SQLite integrity check passed."


def create_backup(source_db, destination):
    """Copy a live database with SQLite's online backup API, then verify it.

    The copy is written to a ``.partial`` file and only renamed into place once
    it passes verification, so a failed backup never looks like a good one.
    """
    source = Path(source_db)
    destination = Path(destination)

    if not source.is_file():
        raise BackupError("Database file not found.")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"Cannot create backup directory: {exc}") from exc

    partial = destination.with_name(f"{destination.name}.partial")
    try:
        partial.unlink(missing_ok=True)
        with closing(sqlite3.connect(str(source))) as source_conn:
            with closing(sqlite3.connect(str(partial))) as target_conn:
                source_conn.backup(target_conn)

        ok, message = verify_backup(partial)
        if not ok:
            raise BackupError(message)

        os.replace(partial, destination)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(f"Backup failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)

    return destination


def _close_database_connections():
    """Close Django's connections so the file can be replaced on Windows."""
    try:
        from django.db import connections
    except Exception:  # pragma: no cover - settings not configured
        return

    for connection in connections.all():
        try:
            connection.close()
        except Exception:  # pragma: no cover - best effort during restore
            pass


def restore_backup(backup_path, db_path):
    """Verify a backup, snapshot the live database, then replace it atomically.

    Returns the path of the safety backup, or ``None`` when there was no live
    database to preserve. Raises :class:`BackupError` without touching the live
    database if the chosen file does not pass verification.
    """
    backup = Path(backup_path)
    live = Path(db_path)

    ok, message = verify_backup(backup)
    if not ok:
        raise BackupError(f"Refusing to restore: {message}")

    safety_path = None
    if live.is_file():
        safety_path = backup.parent / timestamped_name(
            "safety_before_restore"
        )
        create_backup(live, safety_path)

    _close_database_connections()

    # A WAL/SHM pair belonging to the replaced database must never be replayed
    # over the restored file.
    for suffix in ("-wal", "-shm"):
        live.with_name(live.name + suffix).unlink(missing_ok=True)

    partial = live.with_name(f"{live.name}.restore-partial")
    try:
        shutil.copy2(backup, partial)
        ok, message = verify_backup(partial)
        if not ok:
            raise BackupError(f"Restore copy failed verification: {message}")

        os.replace(partial, live)
    except (sqlite3.Error, OSError) as exc:
        raise BackupError(f"Restore failed: {exc}") from exc
    finally:
        partial.unlink(missing_ok=True)

    return safety_path
