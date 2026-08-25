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


async def test_changing_gpu_select_persists_immediately() -> None:
    # No Save button any more — each Select saves on change, matching
    # XLabs' pattern (and closing the "Settings kosong, tidak ada select
    # value" gap: previously these were free-text Inputs that always
    # rendered empty since nothing had ever been typed into them).
    from textual.widgets import Select

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
            gpu_select = app.screen.query_one("#settings-gpu", Select)
            gpu_select.value = "zink"
            await pilot.pause()

        from app import config

        check(config.get("GPU_PROFILE") == "zink", "GPU Select change wasn't persisted")
    finally:
        const.CONFIG_FILE = original
        if os.path.exists(path):
            os.remove(path)


async def test_changing_storage_link_select_persists_immediately() -> None:
    from textual.widgets import Select

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
            storage_select = app.screen.query_one("#settings-storage", Select)
            storage_select.value = "unified-home"
            await pilot.pause()

        from app import config

        check(config.get("STORAGE_LINK") == "unified-home", "Storage Select change not persisted")
    finally:
        const.CONFIG_FILE = original
        if os.path.exists(path):
            os.remove(path)


async def test_settings_selects_show_real_options_not_empty() -> None:
    # The literal complaint this fixes: dropdowns must actually list
    # choices, not render blank with nothing to pick.
    from textual.widgets import Select

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        ids = ("#settings-gpu", "#settings-storage", "#settings-x11", "#settings-audio")
        for widget_id in ids:
            select = app.screen.query_one(widget_id, Select)
            check(len(select._options) > 0, f"{widget_id} has no options")
            check(select.value is not None, f"{widget_id} has no value selected")


async def test_changing_audio_select_persists_immediately() -> None:
    from textual.widgets import Select

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
            audio_select = app.screen.query_one("#settings-audio", Select)
            check(audio_select.value == "off", "audio must default to off in the UI too")
            audio_select.value = "on"
            await pilot.pause()

        from app.native import audio

        check(audio.is_enabled() is True, "Audio Select change wasn't persisted")
    finally:
        const.CONFIG_FILE = original
        if os.path.exists(path):
            os.remove(path)


async def test_apply_font_warns_when_path_empty() -> None:
    from app.screens.common import ActionScreen

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        await pilot.click("#apply-font")
        await pilot.pause()
        still_here = isinstance(app.screen, SettingsScreen)
        check(still_here, "Apply with an empty path must not navigate")
        check(not isinstance(app.screen, ActionScreen), "must not start an action with no path")


async def test_apply_font_pushes_action_screen_when_path_given() -> None:
    from textual.widgets import Input

    from app.screens.common import ActionScreen

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        app.screen.query_one("#settings-font-path", Input).value = "/tmp/whatever.ttf"
        await pilot.click("#apply-font")
        await pilot.pause()
        check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")


async def test_bench_gpu_button_pushes_action_screen() -> None:
    from app.screens.common import ActionScreen

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        await pilot.click("#bench-gpu")
        await pilot.pause()
        check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")


async def test_test_audio_button_pushes_action_screen() -> None:
    from app.screens.common import ActionScreen

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        await pilot.click("#settings")
        await pilot.pause()
        await pilot.click("#test-audio")
        await pilot.pause()
        check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")


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
    test_changing_gpu_select_persists_immediately,
    test_changing_storage_link_select_persists_immediately,
    test_settings_selects_show_real_options_not_empty,
    test_changing_audio_select_persists_immediately,
    test_apply_font_warns_when_path_empty,
    test_apply_font_pushes_action_screen_when_path_given,
    test_bench_gpu_button_pushes_action_screen,
    test_test_audio_button_pushes_action_screen,
    test_uninstall_removes_launcher_and_config,
    test_uninstall_is_idempotent_when_already_gone,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
