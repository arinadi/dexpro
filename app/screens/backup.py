"""Backup screen — native home backup for now. Per-container backup/
restore UI is left as follow-up (the backend, app/backup.py, already
supports it via box/manager.py's proot-distro backup/restore wrapping —
build-task-phase4.md Task 8).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label

from .. import backup as backup_mod
from .common import ActionScreen


class BackupScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Backup")
            with Horizontal():
                yield Button("Backup native home", id="backup-home")
                yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "backup-home":
            self.app.push_screen(ActionScreen("Backing up home", self._backup_home))

    def _backup_home(self, logger) -> None:
        backup_mod.backup_native_home(log=logger)
