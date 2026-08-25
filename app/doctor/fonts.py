"""Font setup for the native layer — ported from XLabs' fonts.py near-
verbatim (build-task-phase4.md Task 5).

Scope change from the source: this applies directly to the native
layer's own font cache/config (~/.config/xfce4/terminal/terminalrc),
not inside a container — simpler than XLabs since there's no proot
boundary to cross.
"""

from __future__ import annotations

import configparser
import os
import subprocess
from collections.abc import Callable

Log = Callable[[str], None]

PACKAGES: tuple[str, ...] = ("fonts-noto-color-emoji", "fonts-firacode")

TERMINALRC_PATH = os.path.expanduser("~/.config/xfce4/terminal/terminalrc")
FONT_NAME = "Fira Code 11"


def install(log: Log | None = None) -> bool:
    install_cmd = ["pkg", "install", "-y", *PACKAGES]
    if log:
        log(f"$ {' '.join(install_cmd)}")
    try:
        subprocess.run(install_cmd, capture_output=True, timeout=120, check=True)
        if log:
            log("$ fc-cache -f")
        subprocess.run(["fc-cache", "-f"], capture_output=True, timeout=60, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: font install failed: {exc}")
        return False


def patch_terminal_font(path: str | None = None, log: Log | None = None) -> bool:
    """Surgically updates the [Configuration] section's font key —
    doesn't touch any other user setting in the file, matching XLabs'
    _patch_ini_section approach (its own docstring: "doesn't clobber
    other user settings")."""
    path = path or TERMINALRC_PATH
    parser = configparser.ConfigParser(strict=False)
    parser.optionxform = str  # preserve key case — xfce4's config is case-sensitive
    if os.path.exists(path):
        try:
            parser.read(path)
        except configparser.Error as exc:
            if log:
                log(f"error: could not parse {path}: {exc}")
            return False
    if "Configuration" not in parser:
        parser["Configuration"] = {}
    parser["Configuration"]["FontName"] = FONT_NAME
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            parser.write(f, space_around_delimiters=False)
        if log:
            log(f"set FontName={FONT_NAME} in {path}")
        return True
    except OSError as exc:
        if log:
            log(f"error: could not write {path}: {exc}")
        return False
