"""MainScreen navigation — headless via Textual's Pilot, no real terminal,
X11, or Termux needed.

    python tests/test_main_screen.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.app import DexproApp
from app.screens import main_screen as main_module
from app.screens.common import ActionScreen
from app.screens.main_screen import MainScreen


async def test_app_starts_on_main_screen() -> None:
    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(isinstance(app.screen, MainScreen), f"got {app.screen!r}")


async def test_main_screen_has_start_and_stop_buttons() -> None:
    from textual.widgets import Button

    app = DexproApp()
    async with app.run_test(size=(80, 40)) as pilot:
        await pilot.pause()
        check(app.screen.query_one("#start", Button) is not None, "Start button missing")
        check(app.screen.query_one("#stop", Button) is not None, "Stop button missing")


def _git(*args, cwd) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=15, check=True)


def test_run_update_pulls_a_real_fast_forward() -> None:
    # Real git, real subprocess — no Termux/Android needed for this half
    # of the module, same philosophy test_backup.py already uses for tar.
    import shutil

    original = const.REPO_DIR
    tmp = tempfile.mkdtemp(prefix="dexpro-update-test-")
    try:
        origin = os.path.join(tmp, "origin.git")
        _git("init", "--bare", "-b", "master", origin, cwd=tmp)

        seed = os.path.join(tmp, "seed")
        _git("clone", origin, seed, cwd=tmp)
        with open(os.path.join(seed, "README"), "w", encoding="utf-8") as f:
            f.write("initial\n")
        _git("add", "README", cwd=seed)
        _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "initial", cwd=seed)
        _git("push", "origin", "master", cwd=seed)

        const.REPO_DIR = os.path.join(tmp, "clone")
        _git("clone", origin, const.REPO_DIR, cwd=tmp)

        # Advance the remote past what REPO_DIR has, exactly the state
        # "pull --ff-only" exists to catch up on.
        with open(os.path.join(seed, "NEW_FILE"), "w", encoding="utf-8") as f:
            f.write("from the update\n")
        _git("add", "NEW_FILE", cwd=seed)
        _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "add file", cwd=seed)
        _git("push", "origin", "master", cwd=seed)

        messages: list[str] = []
        main_module.run_update(messages.append)

        pulled = os.path.join(const.REPO_DIR, "NEW_FILE")
        check(os.path.exists(pulled), "the new commit should have been pulled into REPO_DIR")
        check(any("Up to date" in m for m in messages), f"expected a success message: {messages!r}")
    finally:
        const.REPO_DIR = original
        shutil.rmtree(tmp, ignore_errors=True)


def test_run_update_reports_error_when_not_a_git_repo() -> None:
    original = const.REPO_DIR
    const.REPO_DIR = tempfile.mkdtemp(prefix="dexpro-not-a-repo-")
    try:
        messages: list[str] = []
        main_module.run_update(messages.append)
        check(any("not a git repository" in m for m in messages), f"got {messages!r}")
    finally:
        const.REPO_DIR = original


async def test_update_button_offers_restart() -> None:
    # audit.md item 7: an in-app self-update was one of the explicit gaps
    # (dexpro previously had no update mechanism at all — only the
    # external install.sh). The runner is swapped for a controllable one:
    # the real update finishes instantly with no real checkout here, which
    # would make the "disabled while working" assertion a race — same
    # technique XLabs' own equivalent test uses.
    from textual.widgets import Button

    release = threading.Event()

    def blocking(log) -> None:
        log("pulling")
        release.wait(timeout=15)

    original = main_module.run_update
    main_module.run_update = blocking

    app = DexproApp()
    try:
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            check(app.restart_requested is False, "restart wanted before it was asked for")

            await pilot.click("#update")
            await asyncio.sleep(0.3)

            check(isinstance(app.screen, ActionScreen), f"got {app.screen!r}")
            restart_button = app.screen.query_one("#restart", Button)
            check(restart_button.disabled, "restart was offered while the update was running")

            release.set()
            for _ in range(80):
                await asyncio.sleep(0.1)
                if not app.screen.query_one("#back", Button).disabled:
                    break
            await pilot.pause()

            check(
                not app.screen.query_one("#restart", Button).disabled,
                "restart stayed disabled after the update finished",
            )

            await pilot.click("#restart")
            await pilot.pause()
            check(app.restart_requested, "pressing Restart did not request one")
    finally:
        main_module.run_update = original


TESTS = [
    test_app_starts_on_main_screen,
    test_main_screen_has_start_and_stop_buttons,
    test_run_update_pulls_a_real_fast_forward,
    test_run_update_reports_error_when_not_a_git_repo,
    test_update_button_offers_restart,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
