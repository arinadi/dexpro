"""Termux Store — search/install/uninstall Termux's own packages (not a
dexpro-box container's), plus a Repos screen to enable community repos
(tur-repo and others). The container-scoped Store screen (screens/store.py)
already covers per-box package management; this is the Termux-side
equivalent XLabs' single Store screen provides for its one container —
dexpro needs a separate one since dexpro-box supports N containers plus
the native Termux layer itself.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label

from ..native import packages as native_packages
from .common import ActionScreen


class TermuxStoreScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Termux Store", classes="screen-title")
            yield Input(placeholder="search Termux packages...", id="search")
            yield DataTable(id="package-table")
            with Grid(classes="row3"):
                yield Button("Search", id="do-search")
                yield Button("Install", id="install", variant="success")
                yield Button("Uninstall", id="uninstall", variant="error")
            yield Button("Repos", id="repos")
            yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#package-table", DataTable)
        table.add_columns("Package")
        table.cursor_type = "row"
        self.show_curated()

    def action_back(self) -> None:
        self.app.pop_screen()

    def show_curated(self) -> None:
        table = self.query_one("#package-table", DataTable)
        table.clear()
        for name in native_packages.CURATED_PACKAGES:
            table.add_row(name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "do-search":
            self._search()
        elif event.button.id == "install":
            self._install_selected()
        elif event.button.id == "uninstall":
            self._uninstall_selected()
        elif event.button.id == "repos":
            self.app.push_screen(TermuxReposScreen())

    def _search(self) -> None:
        term = self.query_one("#search", Input).value.strip()
        if not term:
            self.show_curated()
            return
        results = native_packages.search(term)
        table = self.query_one("#package-table", DataTable)
        table.clear()
        for line in results:
            table.add_row(line)
        if not results:
            self.notify("No results.", severity="warning")

    def _selected_package(self) -> str | None:
        table = self.query_one("#package-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        return str(table.get_row_at(table.cursor_row)[0]).split()[0]

    def _install_selected(self) -> None:
        package = self._selected_package()
        if package is None:
            self.notify("Highlight a package first.", severity="warning")
            return

        def _run(logger):
            native_packages.install([package], log=logger)

        self.app.push_screen(ActionScreen(f"Installing {package}", _run))

    def _uninstall_selected(self) -> None:
        package = self._selected_package()
        if package is None:
            self.notify("Highlight a package first.", severity="warning")
            return

        def _run(logger):
            native_packages.uninstall([package], log=logger)

        self.app.push_screen(ActionScreen(f"Uninstalling {package}", _run))


class TermuxReposScreen(Screen):
    """Enable Termux's own official repos (x11-repo/tur-repo are already
    enabled by install.py; the rest are opt-in from here)."""

    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Termux Repos", classes="screen-title")
            yield DataTable(id="repo-table")
            # Grid(row3), not a bare Horizontal: Button#back's width:100%
            # overflows a plain Horizontal row when the siblings (Enable/
            # Refresh) have no width override of their own.
            with Grid(classes="row3"):
                yield Button("Enable", id="enable", variant="success")
                yield Button("Refresh", id="refresh")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#repo-table", DataTable).add_columns("", "Repo", "Description")
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _fill(self) -> None:
        enabled = native_packages.enabled_repos()
        table = self.query_one("#repo-table", DataTable)
        table.clear()
        for name, description in native_packages.REPOS:
            mark = "●" if name in enabled else "○"
            table.add_row(mark, name, description)

    def _selected_repo(self) -> str | None:
        table = self.query_one("#repo-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        return str(table.get_row_at(table.cursor_row)[1])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self._fill()
        elif event.button.id == "enable":
            self._enable_selected()

    def _enable_selected(self) -> None:
        name = self._selected_repo()
        if name is None:
            self.notify("Highlight a repo first.", severity="warning")
            return
        if name in native_packages.enabled_repos():
            self.notify(f"{name} is already enabled.")
            return

        def _run(logger):
            native_packages.enable_repo(name, log=logger)

        self.app.push_screen(ActionScreen(f"Enabling {name}", _run))
