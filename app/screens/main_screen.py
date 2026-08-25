"""Main menu — Grid layout (not Horizontal, which gave XLabs' MainScreen
equal-share button widths that overflowed narrow phone terminals)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import Screen
from textual.widgets import Button, Footer, Header

from .common import ActionScreen


class MainScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="menu"):
            yield Button("Start", id="start")
            yield Button("Stop", id="stop")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.app.push_screen(ActionScreen("Starting dexpro session", self._start))
        elif event.button.id == "stop":
            self.app.push_screen(ActionScreen("Stopping dexpro session", self._stop))

    def _start(self, logger) -> None:
        logger.write("starting native session...")
        self.app.lifecycle.start()
        logger.write("session started")

    def _stop(self, logger) -> None:
        logger.write("stopping native session...")
        self.app.lifecycle.stop()
        logger.write("session stopped")
