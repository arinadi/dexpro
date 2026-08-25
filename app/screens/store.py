"""Store screen — curated packages + search, sitting on top of Phase
2's box/packages.py with a container selector (build-task-phase5.md
Task 4), plus Mirror and Repos screens on top of box/mirror.py — closing
the audit.md gap where that backend had no UI at all.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label

from ..box import mirror as box_mirror
from ..box import packages as box_packages
from .common import ActionScreen


class StoreScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Store — {self._container}")
            yield Input(placeholder="search packages...", id="search")
            yield DataTable(id="package-table")
            with Grid(classes="row3"):
                yield Button("Search", id="do-search")
                yield Button("Install", id="install", variant="success")
                yield Button("Uninstall", id="uninstall", variant="error")
            with Horizontal():
                yield Button("Mirror", id="mirror")
                yield Button("Repos", id="repos")
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

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "do-search":
            self._search()
        elif event.button.id == "install":
            self._install_selected()
        elif event.button.id == "uninstall":
            self._uninstall_selected()
        elif event.button.id == "mirror":
            self.app.push_screen(MirrorScreen(self._container))
        elif event.button.id == "repos":
            self.app.push_screen(ReposScreen(self._container))

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
        container = self._container

        def _run(logger):
            box_packages.install(container, [package], log=logger)

        self.app.push_screen(ActionScreen(f"Installing {package}", _run))

    def _uninstall_selected(self) -> None:
        package = self._selected_package()
        if package is None:
            self.notify("Highlight a package first.", severity="warning")
            return
        container = self._container

        def _run(logger):
            box_packages.uninstall(container, [package], log=logger)

        self.app.push_screen(ActionScreen(f"Uninstalling {package}", _run))


class MirrorScreen(Screen):
    """Fetch the real Debian mirror masterlist, measure candidates, and
    apply the chosen one to the container's sources file."""

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container
        self._mirrors: list[dict[str, str]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Mirror — {self._container}")
            yield DataTable(id="mirror-table")
            with Grid(classes="row3"):
                yield Button("Refresh", id="refresh")
                yield Button("Measure", id="measure")
                yield Button("Use", id="use", variant="success")
            yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#mirror-table", DataTable).add_columns("Site", "Archive")
        self._refresh()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _refresh(self) -> None:
        # fetch_masterlist() is a real network call (up to ~15-20s on a
        # slow connection) — must not block the UI thread, same
        # discipline ActionScreen's runners already use for subprocess
        # calls, or the whole TUI freezes with no spinner and no input
        # for the duration.
        self._fetch_worker()

    @work(thread=True, exclusive=True)
    def _fetch_worker(self) -> None:
        text = box_mirror.fetch_masterlist()
        mirrors = box_mirror.parse_masterlist(text) if text else []
        self.app.call_from_thread(self._apply_mirrors, mirrors)

    def _apply_mirrors(self, mirrors: list[dict[str, str]]) -> None:
        self._mirrors = mirrors
        table = self.query_one("#mirror-table", DataTable)
        table.clear()
        for m in mirrors:
            table.add_row(m.get("Site", ""), m.get("Archive-http", ""))
        if not mirrors:
            self.notify("Could not fetch the mirror list — check connectivity.", severity="warning")

    def _selected(self) -> dict[str, str] | None:
        table = self.query_one("#mirror-table", DataTable)
        row = table.cursor_row
        if row is None or not (0 <= row < len(self._mirrors)):
            return None
        return self._mirrors[row]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self._refresh()
        elif event.button.id == "measure":
            self._measure_selected()
        elif event.button.id == "use":
            self._use_selected()

    def _measure_selected(self) -> None:
        candidate = self._selected()
        if candidate is None:
            self.notify("Highlight a mirror first.", severity="warning")
            return
        base = candidate.get("Archive-http", "").rstrip("/")

        def _run(logger):
            speed = box_mirror.measure_speed(f"{base}/dists/trixie/Release")
            if speed is None:
                logger.write("could not measure — mirror unreachable or too slow")
            else:
                logger.write(f"{candidate.get('Site', base)}: {speed:.0f} bytes/s")

        self.app.push_screen(ActionScreen(f"Measuring {candidate.get('Site', base)}", _run))

    def _use_selected(self) -> None:
        candidate = self._selected()
        if candidate is None:
            self.notify("Highlight a mirror first.", severity="warning")
            return
        base = candidate.get("Archive-http", "")
        container = self._container

        def _run(logger):
            box_mirror.apply_mirror(container, base, log=logger)

        self.app.push_screen(ActionScreen(f"Applying {candidate.get('Site', base)}", _run))


class AddRepoScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Add repository — {self._container}")
            yield Input(placeholder="name (e.g. myrepo)", id="repo-name")
            yield Input(placeholder="repo URI (https://...)", id="repo-uri")
            yield Input(placeholder="signing key URL (https://...)", id="repo-key")
            with Horizontal():
                yield Button("Add", id="submit", variant="success")
                yield Button("Back", id="back")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "submit":
            self._submit()

    def _submit(self) -> None:
        name = self.query_one("#repo-name", Input).value.strip()
        uri = self.query_one("#repo-uri", Input).value.strip()
        key_url = self.query_one("#repo-key", Input).value.strip()
        if not (name and uri and key_url):
            self.notify("Fill in all three fields.", severity="warning")
            return
        container = self._container
        self.app.pop_screen()

        def _run(logger):
            box_mirror.add_custom_repo(container, name, uri, key_url, log=logger)

        self.app.push_screen(ActionScreen(f"Adding repo {name}", _run))


class ReposScreen(Screen):
    """Add-only for now: box/mirror.py has add_custom_repo but no
    list/enable/remove for custom repos, unlike XLabs' fuller ReposScreen
    — that would need new backend functions, out of this pass's scope
    (audit.md's recommendation was to expose what mirror.py already has).
    """

    BINDINGS = [("escape", "back", "Back")]

    def __init__(self, container: str) -> None:
        super().__init__()
        self._container = container

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label(f"Repos — {self._container}")
            yield Button("Add repository", id="add", variant="success")
            yield Button("Back", id="back")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "add":
            self.app.push_screen(AddRepoScreen(self._container))
