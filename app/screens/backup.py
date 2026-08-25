"""Backup screen — lists every backup (native home + per-container),
with Backup native home / Restore / Delete. Closes the audit.md gap:
the backend (restore_native_home, backup_container, restore_container)
was already correct and safe, but only "Backup native home" ever had a
button. Per-container backups are created from BoxManagerScreen's own
"Backup" action; this screen lists and manages whatever already exists
in const.BACKUP_DIR regardless of which kind created it.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label

from .. import backup as backup_mod
from .common import ActionScreen, ConfirmScreen


class BackupScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Label("Backup", classes="screen-title")
            yield DataTable(id="backup-table")
            with Grid(classes="row3"):
                yield Button("Backup native home", id="backup-home", variant="success")
                yield Button("Restore", id="restore")
                yield Button("Delete", id="delete", variant="error")
            yield Button("Back", id="back")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._backups: list[backup_mod.Backup] = []

    def on_mount(self) -> None:
        self.query_one("#backup-table", DataTable).add_columns("Name", "Kind", "Size", "Created")
        self._fill()

    def on_screen_resume(self) -> None:
        self._fill()

    def action_back(self) -> None:
        self.app.pop_screen()

    def _fill(self) -> None:
        self._backups = backup_mod.list_backups()
        table = self.query_one("#backup-table", DataTable)
        table.clear()
        for b in self._backups:
            created = b.created.strftime("%Y-%m-%d %H:%M")
            table.add_row(b.name, b.kind, backup_mod.human_size(b.size_bytes), created)

    def _selected(self) -> backup_mod.Backup | None:
        table = self.query_one("#backup-table", DataTable)
        row = table.cursor_row
        if row is None or not (0 <= row < len(self._backups)):
            return None
        return self._backups[row]

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "backup-home":
            self._backup_home()
        elif event.button.id == "restore":
            await self._restore_selected()
        elif event.button.id == "delete":
            await self._delete_selected()

    def _backup_home(self) -> None:
        def run(logger) -> None:
            backup_mod.backup_native_home(log=logger)

        self.app.push_screen(ActionScreen("Backing up home", run))

    async def _restore_selected(self) -> None:
        b = self._selected()
        if b is None:
            self.notify("Highlight a backup first.", severity="warning")
            return

        def run(logger) -> None:
            if b.kind == "native":
                backup_mod.restore_native_home(b.path, log=logger)
            else:
                backup_mod.restore_container(b.path, log=logger)

        target = "the native home" if b.kind == "native" else b.kind
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Restore {b.name}? Replaces {target} with this backup's contents. "
                "The current contents are moved aside, never destructively overwritten."
            )
        )
        if confirmed:
            self.app.push_screen(ActionScreen(f"Restore {b.name}", run))

    async def _delete_selected(self) -> None:
        b = self._selected()
        if b is None:
            self.notify("Highlight a backup first.", severity="warning")
            return

        def run(logger) -> None:
            backup_mod.delete_backup(b, log=logger)

        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Delete {b.name}? This only removes the saved archive.")
        )
        if confirmed:
            self.app.push_screen(ActionScreen(f"Delete {b.name}", run))
