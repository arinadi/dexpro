"""app/native/x11.py: socket path construction and timeout behavior.

The real connect-success path needs a live X11 socket (Termux/device, or
the Docker dev container's XFCE session via docker/dev/dev.sh) — not
something a bare unit test can exercise.

    python tests/test_x11.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import x11


def test_socket_path_matches_display_number() -> None:
    path = x11.socket_path()
    check(path.endswith(f"X{x11._DISPLAY_NUM}"), f"unexpected socket path: {path}")
    check(".X11-unix" in path, f"socket path missing .X11-unix: {path}")


def test_wait_for_socket_times_out_when_absent() -> None:
    start = time.monotonic()
    result = x11.wait_for_socket(timeout=1.0, interval=0.2)
    elapsed = time.monotonic() - start
    check(result is False, "wait_for_socket should report failure when nothing is listening")
    check(elapsed < 3.0, f"wait_for_socket took too long to give up: {elapsed:.1f}s")


def test_start_fails_gracefully_when_binary_missing() -> None:
    # termux-x11 doesn't exist on this dev machine — start() must return
    # None and log, never raise.
    messages: list[str] = []
    proc = x11.start(log=messages.append)
    if proc is None:
        check(any("not installed" in m for m in messages), "no warning logged on missing binary")


TESTS = [
    test_socket_path_matches_display_number,
    test_wait_for_socket_times_out_when_absent,
    test_start_fails_gracefully_when_binary_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
