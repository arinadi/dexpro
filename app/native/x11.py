"""termux-x11 display server lifecycle.

Don't trust the single-line ``termux-x11 :1 -xstartup "..."`` convenience
form's own readiness — poll an actual socket connect first (XLabs'
``wait_for_x11`` approach), per build-task-phase1.md Task 5.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Callable

from .. import const
from . import packages as native_packages

Log = Callable[[str], None]

DISPLAY = ":1"
_DISPLAY_NUM = 1

# Settings screen key + option values, matching XLabs' DRAW_PATH_OPTIONS
# exactly (Settings previously listed these as free text with nothing
# ever reading the key — this is what actually wires it to termux-x11).
X11_FLAGS_KEY = "X11_EXTRA_FLAGS"
DRAW_PATH_FLAGS: dict[str, tuple[str, ...]] = {
    "normal": (),
    "legacy-drawing": ("-legacy-drawing",),
    "force-bgra": ("-force-bgra",),
    "legacy-drawing+force-bgra": ("-legacy-drawing", "-force-bgra"),
}


def draw_path_flags(value: str | None) -> list[str]:
    return list(DRAW_PATH_FLAGS.get(value or "normal", ()))


def socket_path() -> str:
    return os.path.join(const.TMPDIR, ".X11-unix", f"X{_DISPLAY_NUM}")


def start(log: Log | None = None, extra_flags: list[str] | None = None) -> subprocess.Popen | None:
    if not native_packages.ensure_binary("termux-x11", "termux-x11-nightly", log):
        if log:
            log("error: termux-x11 not available")
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
