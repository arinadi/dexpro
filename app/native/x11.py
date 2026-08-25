"""termux-x11 display server lifecycle.

Don't trust the single-line ``termux-x11 :1 -xstartup "..."`` convenience
form's own readiness — poll an actual socket connect first (XLabs'
``wait_for_x11`` approach), per build-task-phase1.md Task 5.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Callable

from .. import const

Log = Callable[[str], None]

DISPLAY = ":1"
_DISPLAY_NUM = 1


def socket_path() -> str:
    return os.path.join(const.TMPDIR, ".X11-unix", f"X{_DISPLAY_NUM}")


def start(log: Log | None = None, extra_flags: list[str] | None = None) -> subprocess.Popen | None:
    if shutil.which("termux-x11") is None:
        if log:
            log("error: termux-x11 not installed")
        return None
    cmd = ["termux-x11", DISPLAY, *(extra_flags or [])]
    try:
        return subprocess.Popen(cmd)
    except OSError as exc:
        if log:
            log(f"error: failed to launch termux-x11: {exc}")
        return None


def wait_for_socket(timeout: float = 15.0, interval: float = 0.25) -> bool:
    path = socket_path()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect(path)
                    return True
            except OSError:
                pass
        time.sleep(interval)
    return False


def stop(log: Log | None = None) -> None:
    _pkill("termux-x11", log)


def _pkill(name: str, log: Log | None) -> None:
    try:
        subprocess.run(["pkill", "-f", name], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        if log:
            log(f"warning: could not signal {name}")
