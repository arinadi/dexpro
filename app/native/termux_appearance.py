"""Termux's own terminal appearance (font/colors) — separate from
doctor/fonts.py's patch_terminal_font(), which targets xfce4-terminal's
config inside the desktop session. This is for the raw Termux prompt
itself: what's visible before a session starts, or during `dexpro box
enter`.

Re-researched from dextop 2026-08-26: it links a font file straight to
``~/.termux/font.ttf`` and reloads via ``termux-reload-settings`` — the
actual, correct Termux customization API (confirmed from dextop's own
preferences_intent, which does exactly this). This is NOT the mechanism
doctor/fonts.py used (`pkg install`-ing Debian-named font packages,
which don't exist in Termux — the bug that check was removed for).

No font file is bundled or fetched here: dextop's own font/color files
are hosted on its own CDN, which dexpro has no business depending on
for its own users. This only provides the (real, correct) mechanism —
copying a .ttf the user already has on-device to where Termux expects
it — not a specific font choice.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable

Log = Callable[[str], None]

FONT_PATH = os.path.expanduser("~/.termux/font.ttf")


def set_font(source_path: str, log: Log | None = None) -> bool:
    """Copies `source_path` to ~/.termux/font.ttf and reloads Termux's
    settings so it takes effect immediately."""
    if not os.path.isfile(source_path):
        if log:
            log(f"error: {source_path} does not exist")
        return False
    try:
        os.makedirs(os.path.dirname(FONT_PATH), exist_ok=True)
        shutil.copyfile(source_path, FONT_PATH)
    except OSError as exc:
        if log:
            log(f"error: could not copy to {FONT_PATH}: {exc}")
        return False
    if log:
        log(f"set {FONT_PATH} from {source_path}")
    return reload_settings(log)


def reload_settings(log: Log | None = None) -> bool:
    if shutil.which("termux-reload-settings") is None:
        if log:
            log("warning: termux-reload-settings not found — restart Termux for it to apply")
        return False
    try:
        subprocess.run(["termux-reload-settings"], capture_output=True, timeout=10, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"warning: termux-reload-settings failed: {exc}")
        return False
