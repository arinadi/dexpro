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


def test_uninstall_removes_launcher_and_config() -> None:
    from app.screens.settings import _uninstall

    original_bin, original_config = const.PREFIX_BIN, const.CONFIG_FILE
    tmp = tempfile.mkdtemp(prefix="dexpro-uninstall-test-")
    const.PREFIX_BIN = tmp
    fd, config_path = tempfile.mkstemp(suffix=".env")
    os.close(fd)
    const.CONFIG_FILE = config_path
    link = os.path.join(tmp, "dexpro")
    with open(link, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n")

    messages: list[str] = []
    try:
        _uninstall(type("Logger", (), {"write": staticmethod(messages.append)})())
        check(not os.path.exists(link), "launcher must be removed")
        check(not os.path.exists(config_path), "config file must be removed")
        removed_msg = any("removed" in m for m in messages)
        check(removed_msg, f"should report what was removed: {messages!r}")
    finally:
        const.PREFIX_BIN, const.CONFIG_FILE = original_bin, original_config
        if os.path.exists(link):
            os.remove(link)
        if os.path.exists(config_path):
            os.remove(config_path)
        os.rmdir(tmp)


def test_uninstall_is_idempotent_when_already_gone() -> None:
    from app.screens.settings import _uninstall

    original_bin, original_config = const.PREFIX_BIN, const.CONFIG_FILE
    tmp = tempfile.mkdtemp(prefix="dexpro-uninstall-test-")
    const.PREFIX_BIN = tmp
    const.CONFIG_FILE = os.path.join(tmp, "does-not-exist.env")

    messages: list[str] = []
    try:
        _uninstall(type("Logger", (), {"write": staticmethod(messages.append)})())
        check(any("already gone" in m for m in messages), f"got {messages!r}")
    finally:
        const.PREFIX_BIN, const.CONFIG_FILE = original_bin, original_config
        os.rmdir(tmp)


TESTS = [
    test_settings_button_opens_settings_screen,
    test_save_persists_a_setting_to_config,
    test_uninstall_removes_launcher_and_config,
    test_uninstall_is_idempotent_when_already_gone,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
