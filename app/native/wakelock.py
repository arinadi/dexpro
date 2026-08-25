"""Wraps termux-wake-lock / termux-wake-unlock.

Ships in core termux-tools (no Termux:API dependency) and takes no
arguments — confirmed from termux-wake-lock.in source:
``am startservice --user $TERMUX__USER_ID -a com.termux.service_wake_lock
com.termux/com.termux.app.TermuxService``.

Confirmed necessary, not optional: Termux's foreground service does NOT
itself acquire a wakelock (TermuxService.java's onCreate() doesn't — the
wakelock is only acquired on this explicit ACTION_WAKE_LOCK intent).
Skipping this call means the session can be doze-throttled mid-use.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

Log = Callable[[str], None]


def acquire(log: Log | None = None) -> bool:
    return _run("termux-wake-lock", log)


def release(log: Log | None = None) -> bool:
    return _run("termux-wake-unlock", log)


def _run(cmd: str, log: Log | None) -> bool:
    if shutil.which(cmd) is None:
        if log:
            log(f"warning: {cmd} not found — session may be doze-throttled")
        return False
    try:
        subprocess.run([cmd], check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if log:
            log(f"warning: {cmd} failed: {exc}")
        return False
