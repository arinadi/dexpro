"""Ensure a native PulseAudio daemon is available for the session.

Deliberate simplification of build-task-phase1.md's original plan: XLabs
probes four unix/tcp/shm methods because its PulseAudio *client* runs
inside a proot'd container and has to reach the *host's* real server
across that boundary. The native session has no such boundary — there is
no container, so there is nothing to cross. Audio is local; this just
needs to ensure a daemon is running.

Enabled/off toggle re-researched from dextop 2026-08-25 after a real
device report that PulseAudio wasn't starting: dextop's own README
documents audio as explicit opt-in, off by default — "it is not
recommended for use as it can be process and cycle intensive on the
device's battery and processor(s)". dextop's actual scripts (dextop,
container-session, termux-system) were checked directly for the exact
mechanism that consumes its dextop-audio toggle file; none of them
were found to read it — the toggle is written on first run but no
grep-able command in the available scripts starts pulseaudio based on
it, so the live trigger (PulseAudio's own client-side autospawn, or an
XFCE-shipped autostart .desktop entry, is the best guess but wasn't
confirmed either way) stays unverified. What IS confirmed from the
README is the *default*: off, opt-in only. dexpro now matches that
default rather than always attempting to start PulseAudio unconditionally
every session, which is the behavior this was previously reported against.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from .. import config

Log = Callable[[str], None]

ENABLED_KEY = "AUDIO_ENABLED"


def is_enabled() -> bool:
    """Off unless explicitly turned on — dextop's own default, not
    dexpro's prior always-on behavior."""
    return config.get(ENABLED_KEY, "") == "on"


def set_enabled(enabled: bool) -> None:
    if enabled:
        config.set_value(ENABLED_KEY, "on")
    else:
        config.unset(ENABLED_KEY)


def is_running() -> bool:
    """Confirmed on-device: `pactl info` autospawns a PulseAudio daemon
    as a side effect of merely checking whether one is running — a
    Doctor status check silently provisioning a resource just by asking
    about it is surprising and wrong for a read-only check. PULSE_AUTOSPAWN=0
    makes this a genuine read-only probe."""
    import os

    env = dict(os.environ, PULSE_AUTOSPAWN="0")
    try:
        result = subprocess.run(
            ["pactl", "info"], capture_output=True, timeout=5, text=True, env=env
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ensure_server(log: Log | None = None) -> bool:
    if is_running():
        return True
    if shutil.which("pulseaudio") is None:
        if log:
            log("warning: pulseaudio not installed — session will run without audio")
        return False
    if log:
        log("$ pulseaudio --start --exit-idle-time=-1")
    try:
        result = subprocess.run(
            ["pulseaudio", "--start", "--exit-idle-time=-1"],
            capture_output=True,
            timeout=15,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        if log:
            log(f"warning: pulseaudio failed to start: {exc}")
        return False
    if result.returncode != 0 and log:
        # Previously only the generic CalledProcessError repr reached
        # the log, which doesn't include stderr — the actual reason
        # (e.g. a stale PID/lock file, no /dev/shm, ...) was invisible.
        log(f"warning: pulseaudio --start exited {result.returncode}: {result.stderr.strip()}")
    return is_running()
