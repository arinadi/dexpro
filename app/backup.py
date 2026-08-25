"""Backup/restore — two scopes (build-task-phase4.md Task 6):

- Native home: a direct host-side tar — genuinely simpler than XLabs'
  approach, since XLabs' reason for running tar *inside* its container
  (--link2symlink hardlink-emulation not surviving a raw host-side copy)
  doesn't apply to a native filesystem.
- Per-container: prefers `proot-distro backup -c zstd` (box/manager.py)
  over hand-rolling a tar-inside-container approach — upstream already
  provides this, don't reimplement it.

Both: write to a temp path first, move into the final backup dir only
once complete (an interrupted backup should never show up as a listed,
restorable one). Restore moves any existing target aside first — never
destructively overwrites.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from typing import NamedTuple

from . import const
from .box import manager as box_manager

Log = Callable[[str], None]


class Backup(NamedTuple):
    path: str
    name: str
    kind: str  # "native" or the container name
    size_bytes: int
    created: datetime


_HOME_RE = re.compile(r"^home-(\d{8}T\d{6}Z)\.tar\.gz$")
_CONTAINER_RE = re.compile(r"^(.+)-(\d{8}T\d{6}Z)\.tar$")


def timestamp(now) -> str:
    """Pure formatting, no wall-clock call — takes an explicit datetime
    so it's testable with a fixed value instead of the real current time."""
    return now.strftime("%Y%m%dT%H%M%SZ")


def _now_timestamp() -> str:
    from datetime import datetime, timezone

    return timestamp(datetime.now(timezone.utc))


def backup_native_home(log: Log | None = None) -> str | None:
    os.makedirs(const.BACKUP_DIR, exist_ok=True)
    stamp = _now_timestamp()
    final_path = os.path.join(const.BACKUP_DIR, f"home-{stamp}.tar.gz")
    home = const.TERMUX_HOME

    os.makedirs(const.TMPDIR, exist_ok=True)
    tmp_path = os.path.join(const.TMPDIR, f".dexpro-backup-{stamp}.tar.gz")
    try:
        subprocess.run(
            ["tar", "czf", tmp_path, "-C", os.path.dirname(home), os.path.basename(home)],
            capture_output=True,
            timeout=600,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: backup failed: {exc}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

    shutil.move(tmp_path, final_path)
    if log:
        log(f"native home backed up to {final_path}")
    return final_path


def restore_native_home(archive_path: str, log: Log | None = None) -> bool:
    home = const.TERMUX_HOME
    if os.path.exists(home):
        aside = f"{home}.bak-{_now_timestamp()}"
        try:
            shutil.move(home, aside)
        except OSError as exc:
            if log:
                log(f"error: could not move aside existing home: {exc}")
            return False
        if log:
            log(f"existing home moved to {aside} — never destructively overwritten")

    try:
        os.makedirs(home, exist_ok=True)
        subprocess.run(
            ["tar", "xzf", archive_path, "-C", os.path.dirname(home)],
            capture_output=True,
            timeout=600,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: restore failed: {exc}")
        return False


def backup_container(
    container: str, compression: str = "zstd", log: Log | None = None
) -> str | None:
    os.makedirs(const.BACKUP_DIR, exist_ok=True)
    output = os.path.join(const.BACKUP_DIR, f"{container}-{_now_timestamp()}.tar")
    ok = box_manager.backup(container, output, compression=compression, log=log)
    return output if ok else None


def restore_container(archive_path: str, log: Log | None = None) -> bool:
    return box_manager.restore(archive_path, log=log)


def parse_backup_filename(filename: str) -> tuple[str, datetime] | None:
    """Pure function: filename -> (kind, created), or None if it matches
    neither backup_native_home's nor backup_container's naming scheme.
    "native" for home-<stamp>.tar.gz, otherwise the container name for
    <container>-<stamp>.tar — parsed from the timestamp already embedded
    in the filename rather than filesystem mtime, so a copied/moved
    archive still reports its real creation time."""
    match = _HOME_RE.match(filename)
    if match:
        return "native", _parse_timestamp(match.group(1))
    match = _CONTAINER_RE.match(filename)
    if match:
        return match.group(1), _parse_timestamp(match.group(2))
    return None


def _parse_timestamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def list_backups() -> list[Backup]:
    if not os.path.isdir(const.BACKUP_DIR):
        return []
    backups = []
    for filename in os.listdir(const.BACKUP_DIR):
        parsed = parse_backup_filename(filename)
        if parsed is None:
            continue
        kind, created = parsed
        path = os.path.join(const.BACKUP_DIR, filename)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        backups.append(
            Backup(path=path, name=filename, kind=kind, size_bytes=size, created=created)
        )
    backups.sort(key=lambda b: b.created, reverse=True)
    return backups


def delete_backup(backup: Backup, log: Log | None = None) -> bool:
    try:
        os.remove(backup.path)
    except OSError as exc:
        if log:
            log(f"error: could not delete {backup.name}: {exc}")
        return False
    if log:
        log(f"deleted {backup.name}")
    return True


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
