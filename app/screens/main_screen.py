"""Main menu — Grid layout (not Horizontal, which gave XLabs' MainScreen
equal-share button widths that overflowed narrow phone terminals).
Grouped into row2 pairs (audit.md: flat single-row grids read as an
unstructured pile of buttons, one of the "TUI mengecewakan" causes)."""

from __future__ import annotations

import os
import subprocess

from textual.app import ComposeResult
from textual.containers import Grid, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header

from .. import const
from .backup import BackupScreen
from .box_manager import BoxManagerScreen
from .common import ActionScreen
from .doctor import DoctorScreen
from .settings import SettingsScreen

# audit.md item 7 decisions, made explicitly rather than left unaddressed:
# - No VNC fallback: native session stays termux-x11-only.
# - No per-utility update: unlike dextop's separately-installed utility
#   scripts, dexpro is one cohesive git-versioned package — "Update"
#   below is a single whole-repo git pull, there is nothing narrower to
#   update.
# - No auto-launch-on-Termux-open: Start stays an explicit, manual tap.
#   Auto-launching a GUI session as a side effect of merely opening a
#   terminal is a surprising default (unlike dextop's own choice, which
#   assumes the device is dedicated to it) and would surprise a user who
#   opened Termux for something unrelated.


def run_update(log) -> None:
    if not os.path.isdir(os.path.join(const.REPO_DIR, ".git")):
        log(f"[red]{const.REPO_DIR} is not a git repository.[/red]")
        return

    log("Pulling latest changes...")
    result = _run_git(["pull", "--ff-only"])
    _log_output(log, result)

    if result.returncode != 0:
        log("")
        log("Fast-forward failed; fetching and resetting to origin/master...")
        _run_git(["fetch", "origin", "master"])
        result = _run_git(["reset", "--hard", "origin/master"])
        _log_output(log, result)

    log("")
    if result.returncode == 0:
        log("[bold green]Up to date.[/bold green]")
        log("Press Restart to relaunch on the new code, or Back to keep")
        log("running the version already loaded.")
    else:
        log("[bold red]Update failed.[/bold red]")


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", const.REPO_DIR, *args], capture_output=True, text=True, timeout=120
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr=str(exc))


def _log_output(log, result: subprocess.CompletedProcess) -> None:
    for stream in (result.stdout, result.stderr):
        text = (stream or "").strip()
        if text:
            log(text)


class MainScreen(Screen):
    BINDINGS = [("q", "app.quit", "Quit")]

    TOOLTIPS = {
        "start": "Start the native desktop session",
        "stop": "Stop the running session",
        "update": "Pull the latest dexpro from git",
        "boxes": "Create, enter, export, backup and manage dexpro-box containers",
        "doctor": "Diagnose and repair the environment",
        "backup": "Back up or restore your native home",
        "settings": "Per-device preferences, saved to .env",
    }

    def on_mount(self) -> None:
        for button_id, text in self.TOOLTIPS.items():
            self.query_one(f"#{button_id}", Button).tooltip = text

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="menu"):
            with Grid(classes="row2"):
                yield Button("Start", id="start", variant="success")
                yield Button("Stop", id="stop", variant="warning")
            with Grid(classes="row3"):
                yield Button("Update", id="update")
                yield Button("Boxes", id="boxes")
                yield Button("Doctor", id="doctor")
            with Grid(classes="row2"):
                yield Button("Backup", id="backup")
                yield Button("Settings", id="settings")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            self.app.push_screen(ActionScreen("Starting dexpro session", self._start))
        elif event.button.id == "stop":
            self.app.push_screen(ActionScreen("Stopping dexpro session", self._stop))
        elif event.button.id == "update":
            self.app.push_screen(ActionScreen("Update", run_update, offer_restart=True))
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
        logger.write("[green]session started[/green]")

    def _stop(self, logger) -> None:
        logger.write("stopping native session...")
        self.app.lifecycle.stop()
        logger.write("[green]session stopped[/green]")
