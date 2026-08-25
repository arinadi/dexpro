"""Box manager screen — list/create/enter/remove dexpro-box containers.

Simplification note: proot-distro's `list` output is plain text (not
JSON, confirmed in box/manager.py), so this table shows Name only, not
the image/size/created-date columns build-task-phase2.md's Task 5
originally sketched — those need manifest.json parsing per container,
left as follow-up rather than guessed at without a real device to
verify the format against.

"Enter" hands the terminal to an interactive login shell via Textual's
App.suspend() — implemented per Textual's documented API, but not
runtime-verified in this session (no real proot-distro container
available to log into on this dev machine).
"""

from __future__ import annotations

import subprocess

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label

from ..box import create as box_create
from ..box import manager
from .common import ActionScreen, ConfirmScreen
from .export_screen import ExportScreen


class CreateBoxScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        with Vertical(id="create-box-dialog"):
            yield Label("Create dexpro-box")
            yield Input(placeholder="name", id="name")
            yield Input(placeholder="image (e.g. debian:13)", id="image", value="debian:13")
            with Horizontal():
                yield Button("Create", id="create", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.app.pop_screen()
            return
        name = self.query_one("#name", Input).value.strip()
        image = self.query_one("#image", Input).value.strip()
        if not name or not image:
            return
        self.app.pop_screen()

        def _create(logger):
            return box_create.create(name, image, log=logger)

        self.app.push_screen(ActionScreen(f"Creating {name}", _create))


class BoxManagerScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="box-table")
            # Grid, not Horizontal — a Horizontal row of six buttons
            # overflows an 80-col terminal and pushes Back out of reach
            # (confirmed: test_boxes_button_opens_box_manager failed
            # with pilot.click("#back") raising OutOfBounds once Export
            # was added as a sixth button). Same fix XLabs' own
            # MainScreen already needed for the same reason.
            with Grid(id="box-actions"):
                yield Button("Create", id="create")
                yield Button("Enter", id="enter")
                yield Button("Export", id="export")
                yield Button("Remove", id="remove")
                yield Button("Refresh", id="refresh")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#box-table", DataTable)
        table.add_columns("Name")
        table.cursor_type = "row"
        self.refresh_table()

    def refresh_table(self) -> None:
        table = self.query_one("#box-table", DataTable)
        table.clear()
        for container in manager.list_containers():
            table.add_row(container["name"])

    def _selected_name(self) -> str | None:
        table = self.query_one("#box-table", DataTable)
        if table.cursor_row is None or table.row_count == 0:
            return None
        return str(table.get_row_at(table.cursor_row)[0])

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.refresh_table()
        elif event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "create":
            self.app.push_screen(CreateBoxScreen())
        elif event.button.id == "remove":
            await self._remove_selected()
        elif event.button.id == "enter":
            self._enter_selected()
        elif event.button.id == "export":
            self._export_selected()

    def _export_selected(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        self.app.push_screen(ExportScreen(name))

    async def _remove_selected(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Remove container '{name}'? This cannot be undone.")
        )
        if confirmed:
            self.app.push_screen(
                ActionScreen(f"Removing {name}", lambda logger: manager.remove(name, log=logger))
            )

    def _enter_selected(self) -> None:
        name = self._selected_name()
        if name is None:
            return
        with self.app.suspend():
            subprocess.run(manager.login_command(name))
        self.refresh_table()
