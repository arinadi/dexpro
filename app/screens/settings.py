"""Settings screen — per-device .env overrides (ported from XLabs —
build-task-phase5.md Task 3).

GPU_PROFILE, STORAGE_LINK, X11_EXTRA_FLAGS, and Audio are real Select
widgets now, matching XLabs' pattern exactly: each is a real, live-
editable choice, saved immediately on change (no separate Save button —
XLabs' own SettingsScreen doesn't have one either). Previously these
were free-text Input boxes that always rendered empty (nothing had ever
been typed into them) with no enumerated choices to see, which read as
"Settings kosong, tidak ada select value" — indistinguishable from
broken.

Audio: off/on, added 2026-08-25 after a real device report that
PulseAudio wasn't starting. Re-researched dextop directly — its README
documents audio as explicit opt-in, off by default, specifically
because it's "process and cycle intensive on the device's battery and
processor(s)". dexpro previously always attempted to start PulseAudio
every session unconditionally; now it matches dextop's off-by-default,
opt-in design (see native/audio.py for what was and wasn't confirmed
about dextop's exact trigger mechanism).

Termux font: re-researched from dextop 2026-08-26. doctor/fonts.py's
approach (`pkg install`-ing Debian-named font packages) was the wrong
mechanism for Termux's own terminal appearance — dextop's own
preferences_intent shows the real one, linking a .ttf straight to
~/.termux/font.ttf and calling termux-reload-settings. No font file is
bundled here (dextop's are hosted on its own CDN, not dexpro's to
depend on) — this just applies a .ttf the user already has on-device.

WM (window manager) was removed outright rather than given a Select:
grepping the codebase found nothing that ever reads that key.
native/session.py hard-codes xfce4-session with no i3 code path ever
built despite PRD.md leaving the WM choice "deferred to Phase 1
implementation." A dropdown offering a choice that silently does
nothing would repeat the exact mistake Settings' old Uninstall button
already made — better to remove a setting with no real referent than
fake one. (AUDIO_METHOD, a different, now-removed key, was cut for the
same reason before Audio's on/off toggle existed.)
"""

from __future__ import annotations

import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from .. import config, const
from ..native import audio, gpu, termux_appearance, x11
from ..native.lifecycle import STORAGE_LINK_KEY
from .common import ActionScreen, ConfirmScreen

STORAGE_LINK_OFF = "off"
STORAGE_LINK_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Off", STORAGE_LINK_OFF),
    ("Unified home (replace home entries from a 'Home'-labeled mount)", "unified-home"),
)

AUDIO_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Off (default — saves battery/CPU)", "off"),
    ("On", "on"),
)

X11_DRAW_PATH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Normal", "normal"),
    ("Legacy drawing (fixes some black screens)", "legacy-drawing"),
    ("Force BGRA (fixes swapped colors)", "force-bgra"),
    ("Legacy drawing + force BGRA", "legacy-drawing+force-bgra"),
)


class SettingsScreen(Screen):
    BINDINGS = [("escape", "back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="settings-form"):
            yield Label("GPU profile")
            with Horizontal():
                yield Select(
                    [(name.replace("_", " ").title(), name) for name in _gpu_preset_names()],
                    id="settings-gpu",
                    allow_blank=False,
                )
                yield Button("Bench", id="bench-gpu")
            yield Label("Storage link")
            yield Select(STORAGE_LINK_OPTIONS, id="settings-storage", allow_blank=False)
            yield Label("termux-x11 rendering")
            yield Select(X11_DRAW_PATH_OPTIONS, id="settings-x11", allow_blank=False)
            yield Label("Audio")
            with Horizontal():
                yield Select(AUDIO_OPTIONS, id="settings-audio", allow_blank=False)
                yield Button("Test", id="test-audio")
            yield Label("Termux font (path to a .ttf already on-device)")
            with Horizontal():
                yield Input(placeholder="/sdcard/Fonts/MyFont.ttf", id="settings-font-path")
                yield Button("Apply", id="apply-font")
            yield Static("", id="settings-status")
            with Horizontal():
                yield Button("Uninstall", id="uninstall", variant="error")
                yield Button("Back", id="back")
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        # Select.Changed fires on the value _refresh() itself just set,
        # dispatched after _refresh() has already returned — comparing
        # against what was just assigned guards that regardless of when
        # the message actually lands (same reasoning as XLabs' own
        # SettingsScreen).
        self._last_gpu = ""
        self._last_storage = ""
        self._last_x11 = ""
        self._last_audio = ""

    def on_mount(self) -> None:
        self._refresh()

    def on_screen_resume(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self._last_gpu = gpu.load_profile().name
        self.query_one("#settings-gpu", Select).value = self._last_gpu
        self._last_storage = config.get(STORAGE_LINK_KEY, "") or STORAGE_LINK_OFF
        self.query_one("#settings-storage", Select).value = self._last_storage
        self._last_x11 = config.get(x11.X11_FLAGS_KEY, "") or "normal"
        self.query_one("#settings-x11", Select).value = self._last_x11
        self._last_audio = "on" if audio.is_enabled() else "off"
        self.query_one("#settings-audio", Select).value = self._last_audio

    def _status(self, message: str) -> None:
        self.query_one("#settings-status", Static).update(message)

    @on(Select.Changed, "#settings-gpu")
    def _gpu_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_gpu:
            return
        preset = gpu.preset_by_name(str(event.value))
        if preset is not None:
            self._last_gpu = preset.name
            gpu.set_profile_manually(preset)
            self._status(f"GPU profile set to {preset.name}.")

    @on(Select.Changed, "#settings-storage")
    def _storage_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_storage:
            return
        self._last_storage = str(event.value)
        if self._last_storage == STORAGE_LINK_OFF:
            config.unset(STORAGE_LINK_KEY)
        else:
            config.set_value(STORAGE_LINK_KEY, self._last_storage)
        self._status("Storage link mode saved — takes effect on next Start.")

    @on(Select.Changed, "#settings-x11")
    def _x11_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_x11:
            return
        self._last_x11 = str(event.value)
        config.set_value(x11.X11_FLAGS_KEY, self._last_x11)
        self._status("termux-x11 rendering mode saved — takes effect on next Start.")

    @on(Select.Changed, "#settings-audio")
    def _audio_changed(self, event: Select.Changed) -> None:
        if str(event.value) == self._last_audio:
            return
        self._last_audio = str(event.value)
        audio.set_enabled(self._last_audio == "on")
        self._status("Audio setting saved — takes effect on next Start.")

    def action_back(self) -> None:
        self.app.pop_screen()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
        elif event.button.id == "uninstall":
            await self._confirm_uninstall()
        elif event.button.id == "apply-font":
            self._apply_font()
        elif event.button.id == "test-audio":
            self._test_audio()
        elif event.button.id == "bench-gpu":
            self._bench_gpu()

    def _bench_gpu(self) -> None:
        def _run(logger):
            result = gpu.bench(logger)
            if result is None:
                logger.write("[red]No candidate preset produced a score.[/red]")
                return False
            preset, score = result
            gpu.save_profile(preset, score)
            logger.write(f"[bold green]Best: {preset.name} (score {score})[/bold green] — saved.")
            return True

        self.app.push_screen(ActionScreen("Benchmarking GPU", _run))

    def _test_audio(self) -> None:
        self.app.push_screen(ActionScreen("Testing audio", audio.test))

    def _apply_font(self) -> None:
        path = self.query_one("#settings-font-path", Input).value.strip()
        if not path:
            self.notify("Enter a path to a .ttf file first.", severity="warning")
            return

        def _run(logger):
            return termux_appearance.set_font(path, log=logger)

        self.app.push_screen(ActionScreen("Applying Termux font", _run))

    async def _confirm_uninstall(self) -> None:
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(
                "Uninstall dexpro? This removes the launcher and config. "
                f"The repo checkout at {const.REPO_DIR} and any dexpro-box "
                "containers are left untouched — remove those yourself if wanted."
            )
        )
        if confirmed:
            self.app.push_screen(ActionScreen("Uninstalling", _uninstall))


def _gpu_preset_names() -> list[str]:
    return [preset.name for preset in gpu.PRESETS]


def _uninstall(logger) -> None:
    link = os.path.join(const.PREFIX_BIN, "dexpro")
    removed = []
    for path in (link, const.CONFIG_FILE):
        try:
            if os.path.islink(path) or os.path.exists(path):
                os.remove(path)
                removed.append(path)
        except OSError as exc:
            logger.write(f"error: could not remove {path}: {exc}")
    if removed:
        logger.write("removed: " + ", ".join(removed))
    else:
        logger.write("nothing to remove — launcher/config were already gone")
    logger.write(f"dexpro uninstalled. Delete {const.REPO_DIR} manually to remove the repo too.")
