"""Main menu — Grid layout (not Horizontal, which gave XLabs' MainScreen
equal-share button widths that overflowed narrow phone terminals)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, Footer, Header

from .backup import BackupScreen
from .box_manager import BoxManagerScreen
from .common import ActionScreen
from .doctor import DoctorScreen
from .settings import SettingsScreen


class MainScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="menu"):
            yield Button("Start", id="start")
            yield Button("Stop", id="stop")
            yield Button("Boxes", id="boxes")
            yield Button("Doctor", id="doctor")
            yield Button("Backup", id="backup")
            yield Button("Settings", id="settings")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.app.push_screen(ActionScreen("Starting dexpro session", self._start))
        elif event.button.id == "stop":
            self.app.push_screen(ActionScreen("Stopping dexpro session", self._stop))
        elif event.button.id == "boxes":
            self.app.push_screen(BoxManagerScreen())
        elif event.button.id == "doctor":
            self.app.push_screen(DoctorScreen())
        elif event.button.id == "backup":
            self.app.push_screen(BackupScreen())
        elif event.button.id == "settings":
            self.app.push_screen(SettingsScreen())

    def _start(self, logger) -> None:
        logger.write("starting native session...")
        self.app.lifecycle.start()
        logger.write("session started")

    def _stop(self, logger) -> None:
        logger.write("stopping native session...")
        self.app.lifecycle.stop()
        logger.write("session stopped")
