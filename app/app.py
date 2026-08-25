"""DexproApp — Textual entrypoint.

Owns the session Lifecycle at the App level (not any individual Screen)
so it survives screen navigation — build-task-phase1.md Task 7, per
Textual's App-level on_mount/on_unmount as the persistent-service pattern.
"""

from __future__ import annotations

import os
import sys

from textual.app import App

from .native.lifecycle import Lifecycle
from .screens.main_screen import MainScreen


class DexproApp(App):
    TITLE = "dexpro"
    CSS_PATH = "app.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.lifecycle = Lifecycle(log=self._log)
        self.restart_requested = False

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def request_restart(self) -> None:
        """Leave Textual first, then main() re-execs the process. Exiting
        before re-executing matters: it restores the terminal out of the
        alternate screen and raw mode — replacing the process from inside
        a running app would leave the terminal wedged."""
        self.restart_requested = True
        self.exit()

    def on_unmount(self) -> None:
        # Best-effort — don't leave a session running if the TUI exits
        # without an explicit Stop. Failures here are non-fatal; there is
        # no screen left to report them to.
        try:
            self.lifecycle.stop()
        except Exception:  # noqa: BLE001
            pass

    def _log(self, message: str) -> None:
        # Minimal diagnostics sink for Phase 1 (Task 9). Full Doctor
        # (collect_diagnostics-equivalent) lands in Phase 4.
        self.log(message)


def main() -> None:
    app = DexproApp()
    app.run()

    if not app.restart_requested:
        return

    # execv, not another App().run(): the point of restarting is to load
    # code that git just changed, and the old modules are already
    # imported — a plain re-run() would keep serving the stale code.
    try:
        os.execv(sys.executable, [sys.executable, "-m", "app.app"])
    except OSError as exc:
        print(f"Could not restart automatically ({exc}).")
        print("Run dexpro again to pick up the update.")


if __name__ == "__main__":
    main()
