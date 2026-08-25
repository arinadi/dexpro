"""Doctor "Dupes" check — Termux vs any dexpro-box container tool
duplication. Ported from XLabs' duplicates.py TERMUX_DUPLICATES dict
(build-task-phase4.md Task 4), deliberately excluding anything dexpro
itself needs (same exclusion rationale as XLabs).

Adapted scope: XLabs checks "Termux vs the one container"; dexpro
checks "Termux vs a given container" — callers loop over
box.manager.list_containers() for a "check all" mode.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from ..box import manager

Log = Callable[[str], None]

# Termux package name -> binary name.
TERMUX_DUPLICATES: dict[str, str] = {
    "nodejs": "node",
    "rust": "rustc",
    "neovim": "nvim",
    "golang": "go",
    "ruby": "ruby",
    "vim": "vim",
    "tmux": "tmux",
    "htop": "htop",
    "jq": "jq",
    "ripgrep": "rg",
    "fd": "fd",
    "fzf": "fzf",
    "make": "make",
    "gcc": "gcc",
    "openssh": "ssh",
}

# Never offer to remove anything dexpro itself needs.
PROTECTED_TERMUX_PACKAGES: frozenset[str] = frozenset(
    {
        "python",
        "git",
        "proot-distro",
        "termux-x11-nightly",
        "pulseaudio",
        "dbus",
        "xfce4",
        "xfce4-terminal",
    }
)


def termux_has(package: str) -> bool:
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", package],
            capture_output=True,
            timeout=10,
            text=True,
        )
        return "install ok installed" in result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def container_has(container: str, binary: str) -> bool:
    full = manager.login_command(container, ["command", "-v", binary])
    try:
        result = subprocess.run(full, capture_output=True, timeout=10, text=True)
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def find_duplicates(container: str) -> list[str]:
    """Termux packages that are (a) installed in Termux, (b) not
    protected, and (c) also provided by the given container. Never
    assumes — checks both sides, same discipline as XLabs."""
    duplicates = []
    for package, binary in TERMUX_DUPLICATES.items():
        if package in PROTECTED_TERMUX_PACKAGES:
            continue
        if termux_has(package) and container_has(container, binary):
            duplicates.append(package)
    return duplicates


def remove_termux_duplicates(packages: list[str], log: Log | None = None) -> bool:
    unknown = [
        p for p in packages if p not in TERMUX_DUPLICATES or p in PROTECTED_TERMUX_PACKAGES
    ]
    if unknown:
        if log:
            log(f"refusing to remove non-allow-listed package(s): {unknown!r}")
        return False
    cmd = ["pkg", "uninstall", "-y", *packages]
    if log:
        log(f"$ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: pkg uninstall failed: {exc}")
        return False
