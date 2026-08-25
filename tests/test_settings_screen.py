"""SettingsScreen navigation and save round-trip — headless via
Textual's Pilot.

    python tests/test_settings_screen.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.app import DexproApp
from app.screens.main_screen import MainScreen
from app.screens.settings import SettingsScreen


async def test_settings_button_opens_settings_screen() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        check(isinstance(app.screen, SettingsScreen), f"got {app.screen!r}")
        await pilot.click("#back")
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_save_persists_a_setting_to_config() -> None:
    from textual.widgets import Input

    original = const.CONFIG_FILE
    fd, path = tempfile.mkstemp(suffix=".env")
    os.close(fd)
    os.remove(path)
    const.CONFIG_FILE = path
    try:
        app = DexproApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            await pilot.click("#settings")
            await pilot.pause()
            gpu_input = app.screen.query_one("#setting-GPU_PROFILE", Input)
            gpu_input.value = "zink"
            await pilot.click("#save")
            await pilot.pause()

        from app import config

        check(config.get("GPU_PROFILE") == "zink", "setting wasn't persisted by Save")
    finally:
        const.CONFIG_FILE = original
        if os.path.exists(path):
            os.remove(path)


TESTS = [
    test_settings_button_opens_settings_screen,
    test_save_persists_a_setting_to_config,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
