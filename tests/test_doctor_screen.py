"""DoctorScreen navigation — headless via Textual's Pilot.

    python tests/test_doctor_screen.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run, wait_for_rows

from app.app import DexproApp
from app.doctor.checks import Issue
from app.screens.common import ActionScreen
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


async def test_fix_isolates_one_failing_issue_from_the_rest() -> None:
    # Regression test for a real report: Fix looked "stuck, no log
    # coming out" — a single fix that raised or ran long left no
    # confirmation of progress, and (before this fix) an exception from
    # one issue's fix() would silently abort the whole batch via
    # ActionScreen's outer catch, with no sign anything after it ran.
    from textual.widgets import Button

    calls: list[str] = []

    def bad_fix(log) -> bool:
        log("attempting the bad fix...")
        raise RuntimeError("boom")

    def good_fix(log) -> bool:
        log("attempting the good fix...")
        calls.append("good")
        return True

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#doctor")
        await pilot.pause()
        await wait_for_rows(pilot, app, "#doctor-table")

        app.screen._issues = [
            Issue("Bad check", False, "broken", fix=bad_fix),
            Issue("Good check", False, "broken too", fix=good_fix),
        ]
        app.screen._run_fixes()
        await pilot.pause()

        check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")
        action_screen = app.screen
        for _ in range(80):
            await asyncio.sleep(0.1)
            if not action_screen.query_one("#back", Button).disabled:
                break
        await pilot.pause()

        check("good" in calls, "the second fix must still run despite the first raising")
        text = "\n".join(action_screen._lines)
        check("Bad check raised" in text, f"the raise should be logged: {text!r}")
        check("Good check: done" in text, f"the success should be logged: {text!r}")
        # The actual bug being fixed: Issue.fix used to take no
        # arguments at all, so a fix's own progress messages (like
        # gpu.bench()'s per-preset "benchmarking..." lines) had no way
        # to reach this log no matter what they did internally.
        must_reach_screen = "fix()'s own log calls must reach the screen"
        check("attempting the bad fix" in text, f"{must_reach_screen}: {text!r}")
        check("attempting the good fix" in text, f"{must_reach_screen}: {text!r}")


TESTS = [
    test_doctor_button_opens_doctor_screen_with_rows,
    test_fix_button_disabled_state_matches_fixable_issues,
    test_fix_isolates_one_failing_issue_from_the_rest,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
