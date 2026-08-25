"""Storage auto-linking — ported from dextop's termux-storage logic
(build-task-phase5.md Task 1).

CAUTION: the volume-ID pattern below is dexpro's own re-derivation, not
a verbatim port. The original research report's regex read as a
garbled character class (`[A0-Z9]{4}-[A0-Z9]{4}`) — build-task-
phase5.md flagged this explicitly as needing re-verification against
termux-storage's actual source before being trusted. This is a
reasonable interpretation (short FAT-style volume ID, or a long UUID),
not a confirmed port.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

Log = Callable[[str], None]

STANDARD_FOLDERS: tuple[str, ...] = (
    "Desktop",
    "Documents",
    "Downloads",
    "Music",
    "Pictures",
    "Public",
    "Templates",
    "Videos",
)

_SHORT_VOLUME_ID = re.compile(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
_LONG_VOLUME_ID = re.compile(r"^[0-9A-Fa-f]{32,40}$")


def is_volume_id(token: str) -> bool:
    return bool(_SHORT_VOLUME_ID.match(token) or _LONG_VOLUME_ID.match(token))


def trigger_storage_permission() -> bool:
    """Exact invocation confirmed from dextop's termux-storage source."""
    cmd = [
        "am",
        "broadcast",
        "--user",
        "0",
        "-e",
        "com.termux.app.reload_style",
        "storage",
        "-a",
        "com.termux.app.reload_style",
        "com.termux",
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def parse_mounts(mounts_text: str) -> list[dict[str, str]]:
    """Parses /proc/mounts-style text, returns entries under /storage
    whose final path component is a volume ID. A pure function — takes
    text rather than reading the file itself, so it's testable without
    a real Android /proc/mounts."""
    entries = []
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        mount_path = parts[1]
        if not mount_path.startswith("/storage/"):
            continue
        token = mount_path.rstrip("/").rsplit("/", 1)[-1]
        if is_volume_id(token):
            entries.append({"mount_path": mount_path, "volume_id": token})
    return entries


def read_storage_label(mount_path: str) -> str | None:
    label_file = os.path.join(mount_path, ".storage")
    try:
        with open(label_file, encoding="utf-8") as f:
            label = f.read().strip()
        return label or None
    except OSError:
        return None


def media_link_name(entry: dict[str, str]) -> str:
    return read_storage_label(entry["mount_path"]) or entry["volume_id"]


def link_primary_storage(media_dir: str, log: Log | None = None) -> bool:
    primary = "/storage/self/primary"
    if not os.path.isdir(primary):
        return False
    return _make_link(primary, os.path.join(media_dir, "primary"), log=log)


def link_external_storage(mounts_text: str, media_dir: str, log: Log | None = None) -> list[str]:
    linked = []
    for entry in parse_mounts(mounts_text):
        name = media_link_name(entry)
        if _make_link(entry["mount_path"], os.path.join(media_dir, name), log=log):
            linked.append(name)
    return linked


def _make_link(source: str, target: str, log: Log | None = None) -> bool:
    try:
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if os.path.islink(target) or os.path.exists(target):
            os.remove(target)
        os.symlink(source, target, target_is_directory=True)
        return True
    except OSError as exc:
        if log:
            log(f"error: could not link {source} -> {target}: {exc}")
        return False


def ensure_standard_folders(home: str, log: Log | None = None) -> list[str]:
    created = []
    for folder in STANDARD_FOLDERS:
        path = os.path.join(home, folder)
        if not os.path.isdir(path):
            try:
                os.makedirs(path)
                created.append(folder)
            except OSError as exc:
                if log:
                    log(f"error: could not create {path}: {exc}")
    return created


def find_home_mount(media_dir: str) -> str | None:
    """Case-insensitive search for a 'Home'-labeled mount under
    media_dir — the unified-home mechanism's opt-in target."""
    if not os.path.isdir(media_dir):
        return None
    for name in os.listdir(media_dir):
        if name.lower() == "home":
            return os.path.join(media_dir, name)
    return None


def link_unified_home(media_dir: str, home: str, log: Log | None = None) -> list[str]:
    """Opt-in (dextop's own default-off behavior for this mode):
    symlinks each top-level entry of a 'Home'-labeled mount into the
    real home directory, replacing existing entries."""
    home_mount = find_home_mount(media_dir)
    if home_mount is None:
        return []
    linked = []
    for name in os.listdir(home_mount):
        source = os.path.join(home_mount, name)
        if _make_link(source, os.path.join(home, name), log=log):
            linked.append(name)
    return linked
