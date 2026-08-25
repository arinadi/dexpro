"""DexproApp — Textual entrypoint.

Owns the session Lifecycle at the App level (not any individual Screen)
so it survives screen navigation — build-task-phase1.md Task 7, per
Textual's App-level on_mount/on_unmount as the persistent-service pattern.
"""

from __future__ import annotations

from textual.app import App

from .native.lifecycle import Lifecycle
from .screens.main_screen import MainScreen


class DexproApp(App):
    TITLE = "dexpro"
    CSS_PATH = "app.tcss"

    def __init__(self) -> None:
        super().__init__()
        self.lifecycle = Lifecycle(log=self._log)

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

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
    DexproApp().run()


if __name__ == "__main__":
    main()
