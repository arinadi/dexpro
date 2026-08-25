"""Per-container package management — ported from XLabs' packages.py
pattern (build-task-phase2.md Task 4): SAFE_TERM allow-list, apt-get
non-interactive, lists_present() gate, curated fallback list —
parameterized per-container instead of XLabs' single hardcoded
container.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable

from . import manager

Log = Callable[[str], None]

# Shell-injection defense by rejection, not escaping — carried forward
# verbatim from XLabs: a security control, not a style choice.
SAFE_TERM = re.compile(r"^[a-z0-9][a-z0-9.+-]{0,63}$")

CURATED_PACKAGES: tuple[str, ...] = (
    "git",
    "build-essential",
    "python3",
    "nodejs",
    "neovim",
    "vim",
    "curl",
    "wget",
    "htop",
    "tmux",
    "jq",
    "ffmpeg",
    "ripgrep",
    "fd-find",
    "unzip",
    "zip",
    "tree",
    "rsync",
    "openssh-client",
)


def is_safe_term(term: str) -> bool:
    return bool(SAFE_TERM.match(term))


def lists_present(name: str, log: Log | None = None) -> bool:
    """A fresh proot-distro image, like XLabs' own container, ships
    without populated apt lists to stay small — search must not
    silently return nothing because of that."""
    script = "ls /var/lib/apt/lists | grep -vE '^(lock|partial|auxfiles)$' | head -1"
    full = manager.login_command(name, ["sh", "-c", script])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, text=True)
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        if log:
            log("warning: could not check apt lists")
        return False


def search(name: str, term: str, log: Log | None = None) -> list[str]:
    if not is_safe_term(term):
        if log:
            log(f"rejected unsafe search term: {term!r}")
        return []
    if not lists_present(name, log=log):
        if log:
            log("apt lists not populated yet — run `apt update` inside the container first")
        return []
    full = manager.login_command(name, ["apt-cache", "search", "--names-only", term])
    try:
        result = subprocess.run(full, capture_output=True, timeout=30, text=True, check=True)
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: search failed: {exc}")
        return []


def update_lists(name: str, log: Log | None = None) -> bool:
    """Runs `apt-get update` inside the container. A fresh proot-distro
    image ships without populated apt lists (lists_present() exists
    because of this) — this is the action that actually populates them,
    previously only ever described in a log message, never executed."""
    command = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "update"]
    return _run(name, command, timeout=180, log=log)


def install(name: str, packages: list[str], log: Log | None = None) -> bool:
    unsafe = [p for p in packages if not is_safe_term(p)]
    if unsafe:
        if log:
            log(f"rejected unsafe package name(s): {unsafe!r}")
        return False
    command = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", *packages]
    return _run(name, command, timeout=300, log=log)


def uninstall(name: str, packages: list[str], log: Log | None = None) -> bool:
    unsafe = [p for p in packages if not is_safe_term(p)]
    if unsafe:
        if log:
            log(f"rejected unsafe package name(s): {unsafe!r}")
        return False
    command = ["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "remove", "-y", *packages]
    return _run(name, command, timeout=120, log=log)


def _run(name: str, command: list[str], timeout: float, log: Log | None) -> bool:
    full = manager.login_command(name, command)
    try:
        subprocess.run(full, capture_output=True, timeout=timeout, check=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc.stderr}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc}")
        return False
