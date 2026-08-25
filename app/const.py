"""Paths and names shared across dexpro.

Mirrors XLabs' installer/const.py in shape. All paths are computed from
environment variables read at import time from module-level names (not
cached into functions) so tests can override them directly, e.g.
``const.CONFIG_FILE = "/tmp/whatever"``.
"""

from __future__ import annotations

import os

TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
TERMUX_HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")

REPO_DIR = os.path.join(TERMUX_HOME, "dexpro")
CONFIG_FILE = os.path.join(REPO_DIR, ".env")

PREFIX_BIN = os.path.join(TERMUX_PREFIX, "bin")
HOME_BIN = os.path.join(TERMUX_HOME, ".local", "bin")
LAUNCHER_SRC = os.path.join(REPO_DIR, "dexpro")

TMPDIR = os.environ.get("TMPDIR", os.path.join(TERMUX_PREFIX, "tmp"))

BACKUP_DIR = os.path.join(TERMUX_HOME, "dexpro-backups")
