"""Store screen — curated packages + search, sitting on top of Phase
2's box/packages.py with a container selector (build-task-phase5.md
Task 4). Mirror/repo controls aren't wired into this screen yet — the
backend (box/mirror.py) is ready; only the package browse/search/
install flow is in the TUI so far.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label

from ..box import packages as box_packages
from .common import ActionScreen


class StoreScreen(Screen):
    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Store — {self._container}")
            yield Input(placeholder="search packages...", id="search")
            yield DataTable(id="package-table")
            with Horizontal():
                yield Button("Search", id="do-search")
                yield Button("Install selected", id="install")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#package-table", DataTable)
        table.add_columns("Package")
        table.cursor_type = "row"
        self.show_curated()

    def show_curated(self) -> None:
        table = self.query_one("#package-table", DataTable)
        table.clear()
        for name in box_packages.CURATED_PACKAGES:
            table.add_row(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "do-search":
            self._search()
        elif event.button.id == "install":
            self._install_selected()

    def _search(self) -> None:
        term = self.query_one("#search", Input).value.strip()
        if not term:
            self.show_curated()
            return
        results = box_packages.search(self._container, term)
        table = self.query_one("#package-table", DataTable)
        table.clear()
        for line in results:
            table.add_row(line)

    def _install_selected(self) -> None:
        table = self.query_one("#package-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return
        package = str(table.get_row_at(table.cursor_row)[0]).split()[0]
        container = self._container

        def _run(logger):
            box_packages.install(container, [package], log=logger)

        self.app.push_screen(ActionScreen(f"Installing {package}", _run))
