"""Shared TUI scaffolding — ported from XLabs' installer/screens/common.py
pattern (build-task-phase1.md Task 1): a confirm gate for destructive
actions, and a background-worker action runner with a throttled progress
log. Every later phase reuses this.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Label, RichLog

PROGRESS_INTERVAL = 1.0


class ConfirmScreen(ModalScreen[bool]):
    """Cancel/Confirm gate. Dismisses with True on Confirm, False otherwise."""

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(self._message)
            yield Button("Confirm", id="confirm", variant="error")
            yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class _Logger:
    """Passed into an ActionScreen's runner. write() always appends;
    progress() throttles to PROGRESS_INTERVAL so a fast loop doesn't
    flood the log widget."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._write = write
        self._last_progress = 0.0

    def write(self, message: str) -> None:
        self._write(message)

    def __call__(self, message: str) -> None:
        # Lets a _Logger be passed anywhere a plain log(msg) callable is
        # expected (native/*.py's `log` parameters).
        self.write(message)

    def progress(self, message: str) -> None:
        now = time.monotonic()
        if now - self._last_progress < PROGRESS_INTERVAL:
            return
        self._last_progress = now
        self._write(message)


class ActionScreen(Screen):
    """Runs `runner(logger)` in a background thread worker, streaming
    output live. Back stays disabled while busy — the confirm-mid-run
    gate XLabs' Start/Stop Desktop screens rely on."""

    def __init__(self, title: str, runner: Callable[[_Logger], None]) -> None:
        super().__init__()
        self._title = title
        self._runner = runner
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield RichLog(id="log")
            yield Button("Back", id="back", disabled=True)

    def on_mount(self) -> None:
        self.run_task()

    @work(thread=True, exclusive=True)
    def run_task(self) -> None:
        self._busy = True
        logger = _Logger(lambda msg: self.app.call_from_thread(self._append_log, msg))
        try:
            self._runner(logger)
        except Exception as exc:  # noqa: BLE001 — surfaced to the log, not swallowed
            logger.write(f"error: {exc}")
        finally:
            self._busy = False
            self.app.call_from_thread(self._enable_back)

    def _append_log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _enable_back(self) -> None:
        self.query_one("#back", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back" and not self._busy:
            self.app.pop_screen()
