"""Electron --no-sandbox patching — ported from XLabs' electron.py
logic (build-task-phase4.md Task 3), scoped per-container.

proot can't back Chromium's SUID/userns sandbox, so Electron apps
(VS Code, etc.) silently fail to launch without --no-sandbox. Patches
the .desktop file in place *inside the container* — independent of
Phase 3's export mechanism, which patches a separately host-copied file.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from ..box import export as box_export
from ..box import manager

Log = Callable[[str], None]

_EXEC_LINE = re.compile(r"^Exec=(.*)$", re.MULTILINE)


def resolve_binary(exec_value: str) -> str:
    """Exec= can carry arguments/field codes (%F etc.) — the binary is
    the first whitespace-separated token."""
    return exec_value.split()[0] if exec_value.strip() else ""


def is_electron_app(container: str, binary_path: str) -> bool:
    """Detected via a chrome-sandbox helper binary next to the resolved
    executable — XLabs' exact detection method."""
    sandbox_helper = os.path.join(os.path.dirname(binary_path), "chrome-sandbox")
    full = manager.login_command(container, ["test", "-f", sandbox_helper])
    try:
        result = subprocess.run(full, capture_output=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def needs_no_sandbox_patch(desktop_content: str) -> bool:
    match = _EXEC_LINE.search(desktop_content)
    if not match:
        return False
    return "--no-sandbox" not in match.group(1)


def patch_no_sandbox(content: str) -> str:
    match = _EXEC_LINE.search(content)
    if not match:
        return content
    exec_value = match.group(1)
    if "--no-sandbox" in exec_value:
        return content
    patched_exec = f"{exec_value} --no-sandbox"
    return _EXEC_LINE.sub(f"Exec={patched_exec}", content, count=1)


def scan_and_patch(container: str, log: Log | None = None) -> list[str]:
    """Finds Electron apps inside the container and patches their
    .desktop files in place. Returns the list of patched paths."""
    patched: list[str] = []
    for desktop_path in box_export.list_desktop_files(container):
        content = _read_desktop_file(container, desktop_path)
        if content is None:
            continue
        match = _EXEC_LINE.search(content)
        if not match:
            continue
        binary = resolve_binary(match.group(1))
        if not binary or not is_electron_app(container, binary):
            continue
        if not needs_no_sandbox_patch(content):
            continue
        new_content = patch_no_sandbox(content)
        if _write_desktop_file(container, desktop_path, new_content, log=log):
            patched.append(desktop_path)
            if log:
                log(f"patched {desktop_path} in '{container}' with --no-sandbox")
    return patched


def _read_desktop_file(container: str, path: str) -> str | None:
    full = manager.login_command(container, ["cat", path])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, text=True, check=True)
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _write_desktop_file(container: str, path: str, content: str, log: Log | None = None) -> bool:
    # Push content into the container via a heredoc through sh -c —
    # same pattern box/create.py uses to write /etc/resolv.conf, since
    # there's no shared filesystem mount to just write the file onto.
    script = f"cat > {path} << 'DEXPRO_EOF'\n{content}DEXPRO_EOF\n"
    full = manager.login_command(container, ["sh", "-c", script])
    try:
        subprocess.run(full, capture_output=True, timeout=15, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: could not write {path}: {exc}")
        return False
