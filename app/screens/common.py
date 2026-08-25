"""Shared TUI scaffolding — ported from XLabs' installer/screens/common.py
pattern (build-task-phase1.md Task 1): a confirm gate for destructive
actions, and a background-worker action runner with a throttled progress
log. Every later phase reuses this.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Label, RichLog

from .. import const

PROGRESS_INTERVAL = 1.0
EXPORT_NAME = "dexpro-last-output.txt"


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


def _to_clipboard(app: App, text: str) -> str | None:
    """Put `text` on a clipboard. Returns how it got there, or None.

    termux-clipboard-set reaches the real Android clipboard but needs the
    termux-api package and the Termux:API app. Textual's own path uses an
    OSC 52 escape, which only lands if the terminal honours it — ported
    from XLabs' common.py exactly.
    """
    if shutil.which("termux-clipboard-set"):
        try:
            result = subprocess.run(["termux-clipboard-set"], input=text, text=True, timeout=10)
            if result.returncode == 0:
                return "the Android clipboard"
        except (OSError, subprocess.SubprocessError):
            pass

    try:
        app.copy_to_clipboard(text)
        return "the terminal clipboard"
    except Exception:  # noqa: BLE001 — clipboard access is inherently unreliable
        return None


def _write_export(text: str) -> str | None:
    """Mirror the copy to a file, next to the repo when there is one."""
    directory = const.REPO_DIR if os.path.isdir(const.REPO_DIR) else tempfile.gettempdir()
    path = os.path.join(directory, EXPORT_NAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except OSError:
        return None


class ActionScreen(Screen):
    """Runs `runner(logger)` in a background thread worker, streaming
    output live. Back stays disabled while busy — the confirm-mid-run
    gate XLabs' Start/Stop Desktop screens rely on.

    Every ActionScreen (Start/Stop/Update/Doctor Fix/Backup/Store/...
    share this one class) gets a Copy button — XLabs' pattern, ported
    here rather than duplicated per screen since dexpro only has this
    one shared log-window implementation.
    """

    BINDINGS = [("escape", "back", "Back"), ("c", "copy", "Copy")]

    def __init__(
        self,
        title: str,
        runner: Callable[[_Logger], None],
        offer_restart: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._runner = runner
        self._offer_restart = offer_restart
        self._busy = False
        # RichLog keeps rendered strips, not text, so the plain lines are
        # kept alongside it for copying/exporting.
        self._lines: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, classes="screen-title")
            # markup=True: runner functions log Rich markup like
            # "[green]done[/green]" for success/failure color-coding —
            # RichLog defaults markup off, which would otherwise print
            # the literal brackets instead of coloring the text.
            # wrap=True: without it, a line longer than the widget's
            # width renders past the log panel's border instead of
            # wrapping inside it (reported live: "log start xfce keluar
            # area log").
            yield RichLog(id="log", markup=True, wrap=True, auto_scroll=True)
            with Horizontal(id="action-buttons"):
                # Labelled "C", not a clipboard glyph — Termux's font
                # cannot be relied on to have one (XLabs' own reasoning).
                yield Button("C", id="copy")
                if self._offer_restart:
                    yield Button("Restart", id="restart", variant="success", disabled=True)
                yield Button("Back", id="back", disabled=True)

    def on_mount(self) -> None:
        self.query_one("#copy", Button).tooltip = "Copy this log"
        if self._offer_restart:
            self.query_one("#restart", Button).tooltip = "Relaunch dexpro on the new code"
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
            self.app.call_from_thread(self._finish)

    def _append_log(self, message: str) -> None:
        self._lines.append(Text.from_markup(message).plain)
        self.query_one("#log", RichLog).write(message)

    def _finish(self) -> None:
        back = self.query_one("#back", Button)
        back.disabled = False
        if self._offer_restart:
            restart = self.query_one("#restart", Button)
            restart.disabled = False
            restart.focus()
        else:
            back.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy":
            self.action_copy()
            return
        if self._busy:
            return
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "restart":
            self.app.request_restart()

    def action_copy(self) -> None:
        text = "\n".join(self._lines).strip()
        if not text:
            self.notify("Nothing to copy yet.", severity="warning")
            return

        where = _to_clipboard(self.app, text)
        path = _write_export(text)

        if where and path:
            self.notify(f"Copied to {where}. Also saved to {path}")
        elif where:
            self.notify(f"Copied to {where}.")
        elif path:
            self.notify(f"No clipboard available — saved to {path}", severity="warning")
        else:
            self.notify("Could not copy or save the output.", severity="error")

    def action_back(self) -> None:
        if not self._busy:
            self.app.pop_screen()
