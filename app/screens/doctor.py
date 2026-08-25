"""Doctor screen — full checkup, ● present / ○ missing / ? unknown, with
a Fix(N) aggregate action. Build-task-phase4.md Task 8.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid, Vertical
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
            # Grid(row3), not a bare Horizontal: Button#back's width:100%
            # (correct when Back stands alone) fights an auto-width
            # sibling in a plain Horizontal, overflowing the row and
            # clipping whichever button's label lands past the edge —
            # reported live as an invisible Back label, on a screen
            # variant="primary" removal alone didn't fix, because that
            # was never the actual cause here.
            with Grid(classes="row3"):
                yield Button("Fix", id="fix", variant="warning")
                yield Button("Refresh", id="refresh")
                yield Button("Back", id="back")
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
            # Reported live as "stuck, no log": a single "fixing: X" line
            # then nothing until the whole batch finished, since some
            # fixes (pkg install, gpu.bench()) genuinely take a while and
            # nothing confirmed each one actually completed. Explicit
            # before/after lines per item — plus isolating each fix's own
            # exception so one failure doesn't silently abort the rest of
            # the batch (the ActionScreen-level catch would otherwise stop
            # the whole loop on the first raise, with no indication which
            # fix or that anything after it was skipped).
            total = len(fixable)
            logger.write(f"{total} issue(s) to fix")
            for index, issue in enumerate(fixable, start=1):
                logger.write(f"[{index}/{total}] fixing: {issue.name}...")
                try:
                    # logger itself is callable (its __call__ delegates to
                    # write()), which is exactly the plain log(msg) shape
                    # Issue.fix's functions expect — this is the actual
                    # channel that was missing before: fix() took no
                    # arguments at all, so nothing it did internally
                    # (gpu.bench()'s per-preset progress, the $ command
                    # lines added below) could ever reach this screen.
                    ok = issue.fix(logger)
                except Exception as exc:  # noqa: BLE001 — one bad fix must not stop the rest
                    logger.write(f"[{index}/{total}] [red]{issue.name} raised: {exc}[/red]")
                    continue
                if ok:
                    logger.write(f"[{index}/{total}] [green]{issue.name}: done[/green]")
                else:
                    logger.write(f"[{index}/{total}] [red]{issue.name}: failed[/red]")
            logger.write("")
            logger.write("[bold]All fixes attempted.[/bold] Refresh to see the result.")

        self.app.push_screen(ActionScreen("Fixing issues", _run))
