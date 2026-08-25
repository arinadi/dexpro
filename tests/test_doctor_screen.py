"""DoctorScreen navigation — headless via Textual's Pilot.

    python tests/test_doctor_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run, wait_for_rows

from app.app import DexproApp
from app.screens.doctor import DoctorScreen
from app.screens.main_screen import MainScreen


async def test_doctor_button_opens_doctor_screen_with_rows() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#doctor")
        await pilot.pause()
        check(isinstance(app.screen, DoctorScreen), f"got {app.screen!r}")
        rows = await wait_for_rows(pilot, app, "#doctor-table")
        check(rows >= 5, f"expected at least the 5 native checks, got {rows}")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_fix_button_disabled_state_matches_fixable_issues() -> None:
    from textual.widgets import Button

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#doctor")
        await pilot.pause()
        await wait_for_rows(pilot, app, "#doctor-table")
        fixable = [i for i in app.screen._issues if not i.ok and i.fix is not None]
        disabled = app.screen.query_one("#fix", Button).disabled
        msg = f"Fix button disabled={disabled} but {len(fixable)} issues are fixable"
        check(disabled == (not fixable), msg)


TESTS = [
    test_doctor_button_opens_doctor_screen_with_rows,
    test_fix_button_disabled_state_matches_fixable_issues,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
