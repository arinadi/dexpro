"""ExportScreen navigation — headless via Textual's Pilot.

    python tests/test_export_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.app import DexproApp
from app.screens.box_manager import BoxManagerScreen
from app.screens.export_screen import ExportScreen


async def test_export_button_does_nothing_with_no_selection() -> None:
    # No containers exist on this dev machine — the table is empty, so
    # Export must be a no-op rather than crash on a None selection.
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        check(isinstance(app.screen, BoxManagerScreen), f"got {app.screen!r}")
        await pilot.click("#export")
        await pilot.pause()
        still_here = isinstance(app.screen, BoxManagerScreen)
        check(still_here, "Export with no selection must not navigate")


async def test_export_screen_renders_with_empty_container() -> None:
    # Constructed directly (bypassing the no-selection guard above) to
    # confirm the screen itself is well-formed and list_desktop_files()
    # failing gracefully (no proot-distro here) doesn't crash it.
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        app.push_screen(ExportScreen("nonexistent"))
        await pilot.pause()
        check(isinstance(app.screen, ExportScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()


TESTS = [
    test_export_button_does_nothing_with_no_selection,
    test_export_screen_renders_with_empty_container,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
