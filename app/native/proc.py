"""Shared process-kill helper — verify, then escalate.

2026-08-26: added after a real report that "polite kill" wasn't
actually working. Every kill call site in this codebase (lifecycle.py's
session-process sweep, x11.py's termux-x11 kill, gpu.py's
virgl_test_server kill) sent a single, unverified SIGTERM via `pkill`
and moved on — no check that the process actually died, no escalation
if it didn't. XLabs' own stop_desktop() never does that: every kill is
TERM, wait, confirm via `pgrep`, and only then SIGKILL if it's still
alive. This module gives every call site in dexpro the same pattern
instead of each reimplementing (or, as it turned out, not
reimplementing) it.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

Log = Callable[[str], None]


def pgrep(pattern: str) -> bool:
    """True if any running process's command line matches `pattern`."""
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def kill_pattern(pattern: str, log: Log | None = None, wait: float = 3.0) -> bool:
    """TERM, wait up to `wait` seconds confirming via pgrep, then KILL if
    it's still alive. Returns whether `pattern` is confirmed gone
    afterward — never just assumes the signal worked."""
    if not pgrep(pattern):
        return True
    try:
        subprocess.run(["pkill", "-TERM", "-f", pattern], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and pgrep(pattern):
        time.sleep(0.2)
    if not pgrep(pattern):
        return True

    if log:
        log(f"{pattern}: still alive after TERM — sending KILL")
    try:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    time.sleep(0.3)
    gone = not pgrep(pattern)
    if not gone and log:
        log(f"warning: {pattern} survived even SIGKILL")
    return gone
