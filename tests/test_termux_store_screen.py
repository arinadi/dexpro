"""TermuxStoreScreen/TermuxReposScreen navigation — headless via
Textual's Pilot.

    python tests/test_termux_store_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run, wait_for_rows

from app.app import DexproApp
from app.screens.main_screen import MainScreen
from app.screens.termux_store import TermuxReposScreen, TermuxStoreScreen


async def test_termux_button_opens_termux_store() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#termux")
        await pilot.pause()
        check(isinstance(app.screen, TermuxStoreScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_termux_store_shows_curated_packages() -> None:
    from app.native import packages as native_packages

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#termux")
        await pilot.pause()
        rows = await wait_for_rows(pilot, app, "#package-table")
        expected = len(native_packages.CURATED_PACKAGES)
        check(rows == expected, f"expected the curated list ({expected} rows), got {rows}")


async def test_termux_repos_button_opens_repos_screen() -> None:
    from app.native import packages as native_packages

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#termux")
        await pilot.pause()
        await pilot.click("#repos")
        await pilot.pause()
        check(isinstance(app.screen, TermuxReposScreen), f"got {app.screen!r}")
        rows = await wait_for_rows(pilot, app, "#repo-table")
        check(rows == len(native_packages.REPOS), f"expected every repo listed, got {rows} rows")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, TermuxStoreScreen), f"got {app.screen!r}")


TESTS = [
    test_termux_button_opens_termux_store,
    test_termux_store_shows_curated_packages,
    test_termux_repos_button_opens_repos_screen,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
