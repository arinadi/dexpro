"""BoxManagerScreen navigation — headless via Textual's Pilot.

    python tests/test_box_manager_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.app import DexproApp
from app.screens.box_manager import BoxManagerScreen
from app.screens.main_screen import MainScreen


async def test_boxes_button_opens_box_manager() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        check(isinstance(app.screen, BoxManagerScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_box_table_loads_without_proot_distro_installed() -> None:
    # No proot-distro on this dev machine — the table must render empty,
    # not crash the screen.
    from textual.widgets import DataTable

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        table = app.screen.query_one("#box-table", DataTable)
        check(table.row_count == 0, f"expected an empty table, got {table.row_count} rows")


async def test_backup_button_does_nothing_with_no_selection() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        await pilot.click("#backup")
        await pilot.pause()
        still_here = isinstance(app.screen, BoxManagerScreen)
        check(still_here, "Backup with no selection (empty table) must not navigate")


async def test_iobench_button_does_nothing_with_no_selection() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#boxes")
        await pilot.pause()
        await pilot.click("#iobench")
        await pilot.pause()
        still_here = isinstance(app.screen, BoxManagerScreen)
        check(still_here, "IO Bench with no selection (empty table) must not navigate")


TESTS = [
    test_boxes_button_opens_box_manager,
    test_box_table_loads_without_proot_distro_installed,
    test_backup_button_does_nothing_with_no_selection,
    test_iobench_button_does_nothing_with_no_selection,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
