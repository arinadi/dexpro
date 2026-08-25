"""app/screens/common.py: ActionScreen's Copy button and RichLog
wrapping — headless via Textual's Pilot, no clipboard/Termux needed.

    python tests/test_action_screen.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.app import DexproApp
from app.screens.common import ActionScreen, _write_export


def test_write_export_uses_repo_dir_when_it_exists() -> None:
    original = const.REPO_DIR
    const.REPO_DIR = tempfile.mkdtemp(prefix="dexpro-export-test-")
    try:
        path = _write_export("hello")
        check(path is not None, "export should succeed")
        check(path.startswith(const.REPO_DIR), f"expected it under REPO_DIR, got {path!r}")
        with open(path, encoding="utf-8") as f:
            check(f.read() == "hello", "exported content must match what was written")
    finally:
        const.REPO_DIR = original


def test_write_export_falls_back_to_tempdir_when_repo_dir_missing() -> None:
    original = const.REPO_DIR
    const.REPO_DIR = os.path.join(tempfile.gettempdir(), "definitely-not-a-real-dexpro-checkout")
    try:
        path = _write_export("hello")
        check(path is not None, "export should still succeed via the tempdir fallback")
        check(not path.startswith(const.REPO_DIR), "must not have used the nonexistent REPO_DIR")
    finally:
        const.REPO_DIR = original


async def test_copy_button_exists_and_survives_a_click() -> None:
    from textual.widgets import Button

    def run_action(logger) -> None:
        logger.write("hello from the action")

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ActionScreen("Test action", run_action))
        await pilot.pause()

        check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not app.screen.query_one("#back", Button).disabled:
                break
        await pilot.pause()

        check("hello from the action" in app.screen._lines, f"got {app.screen._lines!r}")
        await pilot.click("#copy")
        await pilot.pause()
        # No assertion on where it landed (clipboard availability varies
        # by environment) — this just confirms Copy doesn't crash the
        # screen and the plain-text lines it copies are the real log
        # content, markup already stripped.


async def test_copy_notifies_when_nothing_logged_yet() -> None:
    def run_action(logger) -> None:
        import time

        # Blocks the worker briefly so the log is still empty when Copy
        # is clicked right after the screen mounts.
        time.sleep(0.4)
        logger.write("late line")

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ActionScreen("Test action", run_action))
        await pilot.pause()
        check(app.screen._lines == [], "log should still be empty at this point")
        await pilot.click("#copy")
        await pilot.pause()
        # Reaching here without an exception is the assertion; the
        # notify() call itself isn't introspectable via Pilot.


TESTS = [
    test_write_export_uses_repo_dir_when_it_exists,
    test_write_export_falls_back_to_tempdir_when_repo_dir_missing,
    test_copy_button_exists_and_survives_a_click,
    test_copy_notifies_when_nothing_logged_yet,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
