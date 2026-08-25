"""MainScreen navigation — headless via Textual's Pilot, no real terminal,
X11, or Termux needed.

    python tests/test_main_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.app import DexproApp
from app.screens.main_screen import MainScreen


async def test_app_starts_on_main_screen() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_main_screen_has_start_and_stop_buttons() -> None:
    from textual.widgets import Button

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(app.screen.query_one("#start", Button) is not None, "Start button missing")
        check(app.screen.query_one("#stop", Button) is not None, "Stop button missing")


TESTS = [
    test_app_starts_on_main_screen,
    test_main_screen_has_start_and_stop_buttons,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
