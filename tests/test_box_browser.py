"""app/box/browser.py: Firefox "safe tier" proot-overhead tuning,
without a real proot-distro container on this dev machine.

    python tests/test_box_browser.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import browser


def test_firefox_present_false_for_nonexistent_container() -> None:
    check(browser.firefox_present("definitely-not-a-real-container") is False, "no such container")


def test_firefox_video_prefs_ok_false_for_nonexistent_container() -> None:
    result = browser.firefox_video_prefs_ok("definitely-not-a-real-container")
    check(result is False, "no such container — nothing can be 'ok'")


def test_apply_firefox_tuning_fails_gracefully_for_nonexistent_container() -> None:
    messages: list[str] = []
    result = browser.apply_firefox_tuning("definitely-not-a-real-container", log=messages.append)
    check(result is False, "must report failure, not raise, for a nonexistent container")
    check(any("no such container" in m for m in messages), f"got {messages!r}")


TESTS = [
    test_firefox_present_false_for_nonexistent_container,
    test_firefox_video_prefs_ok_false_for_nonexistent_container,
    test_apply_firefox_tuning_fails_gracefully_for_nonexistent_container,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
