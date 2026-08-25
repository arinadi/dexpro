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

# A single, dexpro-controlled XDG_RUNTIME_DIR — deliberately NOT
# "respect whatever's already in the environment, else fall back to
# this": that's what the native session's own script used to do, and
# native/audio.py's PulseAudio calls never agreed with it (each computed
# its own value independently). PulseAudio's real runtime socket lives
# at $XDG_RUNTIME_DIR/pulse/native — Settings' Audio Test worked (every
# audio.py call shares the same ambient environment), but the XFCE
# session script guessed a different, wrong path, so apps inside the
# actual desktop couldn't find the socket at all. Fixed by pointing both
# sides at this exact same constant instead of two independent guesses.
XDG_RUNTIME_DIR = os.path.join(TMPDIR, "dexpro-runtime")

BACKUP_DIR = os.path.join(TERMUX_HOME, "dexpro-backups")

# dextop's own convention for where linked storage mounts live.
MEDIA_DIR = os.path.join(TERMUX_PREFIX, "media")
