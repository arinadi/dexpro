"""Settings screen — per-device .env overrides, using config.py's
KEY=value pattern directly (ported from XLabs — build-task-phase5.md
Task 3).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from .. import config
from .common import ConfirmScreen

SETTINGS_KEYS: tuple[tuple[str, str], ...] = (
    ("GPU_PROFILE", "GPU profile override (software/virgl/zink/turnip)"),
    ("AUDIO_METHOD", "Audio method override"),
    ("WM", "Window manager (xfce/i3)"),
    ("STORAGE_LINK", "Storage link mode (unset or 'unified-home')"),
    ("X11_EXTRA_FLAGS", "termux-x11 diagnostic flags (-legacy-drawing, -force-bgra)"),
)


class SettingsScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            for key, label in SETTINGS_KEYS:
                yield Label(label)
                yield Input(value=config.get(key, "") or "", id=f"setting-{key}")
            with Horizontal():
                yield Button("Save", id="save")
                yield Button("Uninstall", id="uninstall", variant="error")
                yield Button("Back", id="back")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "save":
            self._save()
        elif event.button.id == "uninstall":
            await self._confirm_uninstall()

    def _save(self) -> None:
        for key, _label in SETTINGS_KEYS:
            value = self.query_one(f"#setting-{key}", Input).value.strip()
            if value:
                config.set_value(key, value)
            else:
                config.unset(key)

    async def _confirm_uninstall(self) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen("Uninstall dexpro? This removes the launcher and config.")
        )
        if confirmed:
            # Actual removal (launcher symlink, config file) is
            # install.py's domain — this screen gates the confirm;
            # wiring the real removal is follow-up.
            pass
