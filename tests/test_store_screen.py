"""StoreScreen navigation — headless via Textual's Pilot.

    python tests/test_store_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run, wait_for_rows

from app.app import DexproApp
from app.screens.box_manager import BoxManagerScreen
from app.screens.store import StoreScreen


async def test_store_button_does_nothing_with_no_selection() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        await pilot.click("#store")
        await pilot.pause()
        still_here = isinstance(app.screen, BoxManagerScreen)
        check(still_here, "Store with no selection must not navigate")


async def test_store_screen_shows_curated_packages() -> None:
    from app.box import packages as box_packages

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        app.push_screen(StoreScreen("nonexistent"))
        await pilot.pause()
        check(isinstance(app.screen, StoreScreen), f"got {app.screen!r}")
        rows = await wait_for_rows(pilot, app, "#package-table")
        expected = len(box_packages.CURATED_PACKAGES)
        check(rows == expected, f"expected the curated list ({expected} rows), got {rows}")
        await pilot.click("#back")
        await pilot.pause()


TESTS = [
    test_store_button_does_nothing_with_no_selection,
    test_store_screen_shows_curated_packages,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
