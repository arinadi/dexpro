"""app/backup.py: native home backup/restore round-trip, using a real
`tar` (available in this environment via Git Bash/MSYS) against
isolated temp directories — no Termux/container needed for this half of
the module.

    python tests/test_backup.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import backup, const


def test_timestamp_is_pure_and_sortable() -> None:
    a = backup.timestamp(datetime(2026, 8, 25, 13, 0, 0, tzinfo=timezone.utc))
    b = backup.timestamp(datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc))
    check(a < b, "later timestamps must sort after earlier ones as plain strings")
    check(a == "20260825T130000Z", f"unexpected format: {a!r}")


def _isolated_paths(test):
    def wrapper():
        tmp = tempfile.mkdtemp(prefix="dexpro-backup-test-")
        originals = (const.TERMUX_HOME, const.BACKUP_DIR, const.TMPDIR)
        const.TERMUX_HOME = os.path.join(tmp, "home")
        const.BACKUP_DIR = os.path.join(tmp, "backups")
        const.TMPDIR = os.path.join(tmp, "tmp")
        os.makedirs(const.TERMUX_HOME)
        os.makedirs(const.TMPDIR)
        try:
            test()
        finally:
            const.TERMUX_HOME, const.BACKUP_DIR, const.TMPDIR = originals
            shutil.rmtree(tmp, ignore_errors=True)

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated_paths
def test_backup_and_restore_round_trip() -> None:
    marker_path = os.path.join(const.TERMUX_HOME, "canary.txt")
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("dexpro backup test canary\n")

    archive = backup.backup_native_home()
    check(archive is not None, "backup should succeed")
    check(os.path.exists(archive), "backup archive file must exist")
    check(archive.startswith(const.BACKUP_DIR), "archive must land in the configured backup dir")

    # Simulate a subsequent, different home before restoring — proves
    # restore actually replaces content, not just checks the archive
    # exists.
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("this should be replaced by the restore\n")

    restored = backup.restore_native_home(archive)
    check(restored, "restore should succeed")
    with open(marker_path, encoding="utf-8") as f:
        content = f.read()
    expected = "dexpro backup test canary\n"
    check(content == expected, f"restored content doesn't match the backup: {content!r}")


@_isolated_paths
def test_restore_moves_existing_home_aside_instead_of_overwriting() -> None:
    marker_path = os.path.join(const.TERMUX_HOME, "canary.txt")
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("original\n")
    archive = backup.backup_native_home()
    check(archive is not None, "backup should succeed")

    with open(marker_path, "w", encoding="utf-8") as f:
        f.write("current, about to be replaced\n")

    backup.restore_native_home(archive)

    home_dir = os.path.dirname(const.TERMUX_HOME)
    siblings = os.listdir(home_dir)
    prefix = os.path.basename(const.TERMUX_HOME) + ".bak-"
    backups_aside = [s for s in siblings if s.startswith(prefix)]
    msg = f"expected a .bak-<timestamp> sibling from the move-aside, got {siblings!r}"
    check(backups_aside, msg)


@_isolated_paths
def test_backup_is_atomic_and_never_lists_a_failed_attempt() -> None:
    # An interrupted backup must never show up as a listed, restorable
    # backup — verified here by confirming the temp path used during
    # writing is gone and only the final path remains.
    archive = backup.backup_native_home()
    check(archive is not None, "backup should succeed")
    entries = os.listdir(const.BACKUP_DIR)
    expected = [os.path.basename(archive)]
    check(entries == expected, f"backup dir should contain only the final archive, got {entries!r}")
    tmp_leftovers = [f for f in os.listdir(const.TMPDIR) if f.startswith(".dexpro-backup-")]
    check(not tmp_leftovers, f"no temp backup file should be left behind: {tmp_leftovers!r}")


def test_parse_backup_filename_recognizes_native() -> None:
    result = backup.parse_backup_filename("home-20260825T130000Z.tar.gz")
    check(result is not None, "a well-formed native filename must parse")
    kind, created = result
    check(kind == "native", f"expected 'native', got {kind!r}")
    check(created == datetime(2026, 8, 25, 13, 0, 0, tzinfo=timezone.utc), f"got {created!r}")


def test_parse_backup_filename_recognizes_container() -> None:
    result = backup.parse_backup_filename("dev-20260825T130000Z.tar")
    check(result is not None, "a well-formed container filename must parse")
    kind, created = result
    check(kind == "dev", f"expected the container name 'dev', got {kind!r}")
    check(created == datetime(2026, 8, 25, 13, 0, 0, tzinfo=timezone.utc), f"got {created!r}")


def test_parse_backup_filename_none_for_unrelated_file() -> None:
    check(backup.parse_backup_filename("notes.txt") is None, "unrelated files must not parse")


def test_human_size_formats_reasonably() -> None:
    check(backup.human_size(500) == "500B", f"got {backup.human_size(500)!r}")
    check(backup.human_size(2048) == "2.0KB", f"got {backup.human_size(2048)!r}")
    five_mb = 5 * 1024 * 1024
    check(backup.human_size(five_mb) == "5.0MB", f"got {backup.human_size(five_mb)!r}")


@_isolated_paths
def test_list_backups_empty_when_dir_missing() -> None:
    check(backup.list_backups() == [], "no backup dir yet — must return an empty list, not raise")


@_isolated_paths
def test_list_backups_finds_and_sorts_newest_first() -> None:
    os.makedirs(const.BACKUP_DIR, exist_ok=True)
    for name in ("home-20260101T000000Z.tar.gz", "home-20260825T000000Z.tar.gz", "notes.txt"):
        with open(os.path.join(const.BACKUP_DIR, name), "w", encoding="utf-8") as f:
            f.write("x")

    backups = backup.list_backups()
    check(len(backups) == 2, f"the unrelated file must be excluded, got {backups!r}")
    check(backups[0].name == "home-20260825T000000Z.tar.gz", "newest backup must sort first")


@_isolated_paths
def test_delete_backup_removes_the_file() -> None:
    os.makedirs(const.BACKUP_DIR, exist_ok=True)
    path = os.path.join(const.BACKUP_DIR, "home-20260825T000000Z.tar.gz")
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")
    [b] = backup.list_backups()

    ok = backup.delete_backup(b)
    check(ok, "deleting an existing backup should succeed")
    check(not os.path.exists(path), "the archive file must actually be gone")


TESTS = [
    test_timestamp_is_pure_and_sortable,
    test_backup_and_restore_round_trip,
    test_restore_moves_existing_home_aside_instead_of_overwriting,
    test_backup_is_atomic_and_never_lists_a_failed_attempt,
    test_parse_backup_filename_recognizes_native,
    test_parse_backup_filename_recognizes_container,
    test_parse_backup_filename_none_for_unrelated_file,
    test_human_size_formats_reasonably,
    test_list_backups_empty_when_dir_missing,
    test_list_backups_finds_and_sorts_newest_first,
    test_delete_backup_removes_the_file,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
