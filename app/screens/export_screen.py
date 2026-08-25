"""Export screen — list a container's .desktop files, multi-select,
confirm and export via the distrobox-style mechanism in box/export.py.

Binary export (--bin) isn't exposed here yet — .desktop discovery is the
common case (build-task-phase3.md Task 3); a binary picker needs a path
input, not a selection list, and is left as follow-up.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, SelectionList
from textual.widgets.selection_list import Selection

from ..box import export as box_export
from .common import ActionScreen


class ExportScreen(Screen):
    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Export apps from '{self._container}'")
            yield SelectionList(id="desktop-files")
            with Horizontal():
                yield Button("Export selected", id="export")
                yield Button("Refresh", id="refresh")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()

    def refresh_list(self) -> None:
        selection_list = self.query_one("#desktop-files", SelectionList)
        selection_list.clear_options()
        for path in box_export.list_desktop_files(self._container):
            selection_list.add_option(Selection(path, path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self.refresh_list()
        elif event.button.id == "export":
            self._export_selected()

    def _export_selected(self) -> None:
        selection_list = self.query_one("#desktop-files", SelectionList)
        selected = list(selection_list.selected)
        if not selected:
            return
        container = self._container

        def _run(logger):
            for path in selected:
                box_export.export_app(container, path, log=logger)

        self.app.push_screen(ActionScreen(f"Exporting from {container}", _run))
