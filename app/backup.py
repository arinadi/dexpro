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
import shutil
import subprocess
from collections.abc import Callable

from . import const
from .box import manager as box_manager

Log = Callable[[str], None]


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
