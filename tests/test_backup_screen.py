"""BackupScreen navigation — headless via Textual's Pilot.

    python tests/test_backup_screen.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.app import DexproApp
from app.screens.backup import BackupScreen
from app.screens.main_screen import MainScreen


async def test_backup_button_opens_backup_screen() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#backup")
        await pilot.pause()
        check(isinstance(app.screen, BackupScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


TESTS = [
    test_backup_button_opens_backup_screen,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
