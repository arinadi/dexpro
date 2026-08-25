"""app/native/wakelock.py: non-fatal behavior when termux-wake-lock is
absent — true on any non-Termux host, including this dev machine and the
Docker dev container.

    python tests/test_wakelock.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import wakelock


def test_acquire_never_raises_and_logs_on_failure() -> None:
    messages: list[str] = []
    result = wakelock.acquire(log=messages.append)
    check(isinstance(result, bool), "acquire() must return a bool")
    if result is False:
        check(
            any("not found" in m or "failed" in m for m in messages),
            "acquire() failed silently without a warning",
        )


def test_release_never_raises_and_logs_on_failure() -> None:
    messages: list[str] = []
    result = wakelock.release(log=messages.append)
    check(isinstance(result, bool), "release() must return a bool")
    if result is False:
        check(
            any("not found" in m or "failed" in m for m in messages),
            "release() failed silently without a warning",
        )


def test_missing_binary_is_non_fatal_without_a_log_callback() -> None:
    # log is optional — must not raise even when it's None.
    wakelock.acquire(log=None)
    wakelock.release(log=None)


TESTS = [
    test_acquire_never_raises_and_logs_on_failure,
    test_release_never_raises_and_logs_on_failure,
    test_missing_binary_is_non_fatal_without_a_log_callback,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
