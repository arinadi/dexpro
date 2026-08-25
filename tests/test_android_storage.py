"""app/android/storage.py: mount parsing, label reading, and standard-
folder creation — all genuinely testable locally. Symlink creation
tolerates failure on this Windows dev machine (no elevated privilege),
and is confirmed for real in the Linux Podman container.

    python tests/test_android_storage.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.android import storage


def test_is_volume_id_accepts_short_fat_style_id() -> None:
    check(storage.is_volume_id("1A2B-3C4D"), "should accept a short FAT-style volume ID")


def test_is_volume_id_accepts_long_uuid() -> None:
    check(storage.is_volume_id("a" * 32), "should accept a 32-char UUID-like token")
    check(storage.is_volume_id("a" * 40), "should accept a 40-char UUID-like token")


def test_is_volume_id_rejects_plain_words() -> None:
    check(not storage.is_volume_id("self"), "'self' (as in /storage/self) must not match")
    check(not storage.is_volume_id("primary"), "'primary' must not match")
    check(not storage.is_volume_id(""), "empty string must not match")


def test_parse_mounts_finds_only_storage_entries_with_a_volume_id() -> None:
    mounts_text = "\n".join(
        [
            "/dev/fuse /storage/self fuse rw 0 0",
            "/dev/sdcard1 /storage/1A2B-3C4D fuse rw 0 0",
            "tmpfs /data tmpfs rw 0 0",
            "/dev/sdcard2 /storage/emulated fuse rw 0 0",
        ]
    )
    entries = storage.parse_mounts(mounts_text)
    check(len(entries) == 1, f"expected exactly one real volume entry, got {entries!r}")
    check(entries[0]["volume_id"] == "1A2B-3C4D", f"wrong volume id extracted: {entries[0]!r}")
    check(entries[0]["mount_path"] == "/storage/1A2B-3C4D", "wrong mount path extracted")


def test_parse_mounts_ignores_malformed_lines() -> None:
    result = storage.parse_mounts("garbage\n\nalso garbage")
    check(result == [], "malformed lines must not crash parsing")


def test_read_storage_label_returns_none_when_absent() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        check(storage.read_storage_label(tmp) is None, "no .storage file should mean no label")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_read_storage_label_reads_real_file() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        with open(os.path.join(tmp, ".storage"), "w", encoding="utf-8") as f:
            f.write("MySDCard\n")
        check(storage.read_storage_label(tmp) == "MySDCard", "label not read correctly")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_media_link_name_falls_back_to_volume_id_without_a_label() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        entry = {"mount_path": tmp, "volume_id": "1A2B-3C4D"}
        check(storage.media_link_name(entry) == "1A2B-3C4D", "should fall back to the volume id")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ensure_standard_folders_creates_all_of_them() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        created = storage.ensure_standard_folders(tmp)
        all_created = set(created) == set(storage.STANDARD_FOLDERS)
        check(all_created, f"not all folders created: {created!r}")
        for folder in storage.STANDARD_FOLDERS:
            exists = os.path.isdir(os.path.join(tmp, folder))
            check(exists, f"{folder} wasn't actually created")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ensure_standard_folders_is_idempotent() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        storage.ensure_standard_folders(tmp)
        second_pass = storage.ensure_standard_folders(tmp)
        check(second_pass == [], f"a second pass should create nothing new, got {second_pass!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_find_home_mount_is_case_insensitive() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        os.makedirs(os.path.join(tmp, "HoMe"))
        found = storage.find_home_mount(tmp)
        matched = found is not None and found.endswith("HoMe")
        check(matched, f"case-insensitive match failed: {found!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_find_home_mount_none_when_absent() -> None:
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        check(storage.find_home_mount(tmp) is None, "no Home-labeled dir should mean no match")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_trigger_storage_permission_never_raises() -> None:
    # No `am` binary on this dev machine (Android-only) — must return
    # False, not raise.
    check(isinstance(storage.trigger_storage_permission(), bool), "must return a bool, never raise")


def test_make_link_tolerates_missing_privilege() -> None:
    # Confirmed on this dev machine: os.symlink fails without elevated
    # privilege on Windows. _make_link must catch that and return False
    # rather than propagate the exception — verified for real symlink
    # creation success in the Linux Podman container instead.
    tmp = tempfile.mkdtemp(prefix="dexpro-storage-test-")
    try:
        source = os.path.join(tmp, "source")
        os.makedirs(source)
        target = os.path.join(tmp, "target")
        result = storage._make_link(source, target)
        check(isinstance(result, bool), "must return a bool, never raise")
        if result:
            check(os.path.islink(target), "if it reports success, a link must actually exist")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


TESTS = [
    test_is_volume_id_accepts_short_fat_style_id,
    test_is_volume_id_accepts_long_uuid,
    test_is_volume_id_rejects_plain_words,
    test_parse_mounts_finds_only_storage_entries_with_a_volume_id,
    test_parse_mounts_ignores_malformed_lines,
    test_read_storage_label_returns_none_when_absent,
    test_read_storage_label_reads_real_file,
    test_media_link_name_falls_back_to_volume_id_without_a_label,
    test_ensure_standard_folders_creates_all_of_them,
    test_ensure_standard_folders_is_idempotent,
    test_find_home_mount_is_case_insensitive,
    test_find_home_mount_none_when_absent,
    test_trigger_storage_permission_never_raises,
    test_make_link_tolerates_missing_privilege,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
