"""Doctor screen — full checkup, ● present / ○ missing / ? unknown, with
a Fix(N) aggregate action. Build-task-phase4.md Task 8.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header

from ..doctor import checks
from .common import ActionScreen


def _symbol(issue: checks.Issue) -> str:
    if issue.unknown:
        return "?"
    return "●" if issue.ok else "○"  # ● / ○


class DoctorScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._issues: list[checks.Issue] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="doctor-table")
            with Horizontal():
                yield Button("Fix", id="fix", variant="warning")
                yield Button("Refresh", id="refresh")
                yield Button("Back", id="back", variant="primary")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_mount(self) -> None:
        table = self.query_one("#doctor-table", DataTable)
        table.add_columns("", "Check", "Detail")
        self.refresh_checks()

    def refresh_checks(self) -> None:
        self._issues = checks.run_all_checks()
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        for issue in self._issues:
            table.add_row(_symbol(issue), issue.name, issue.detail)
        fixable = [i for i in self._issues if not i.ok and i.fix is not None]
        self.query_one("#fix", Button).disabled = not fixable

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "refresh":
            self.refresh_checks()
        elif event.button.id == "fix":
            self._run_fixes()

    def _run_fixes(self) -> None:
        fixable = [i for i in self._issues if not i.ok and i.fix is not None]

        def _run(logger):
            for issue in fixable:
                logger.write(f"fixing: {issue.name}")
                issue.fix()

        self.app.push_screen(ActionScreen("Fixing issues", _run))
