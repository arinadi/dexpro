"""Ensure a native PulseAudio daemon is available for the session.

Deliberate simplification of build-task-phase1.md's original plan: XLabs
probes four unix/tcp/shm methods because its PulseAudio *client* runs
inside a proot'd container and has to reach the *host's* real server
across that boundary. The native session has no such boundary — there is
no container, so there is nothing to cross. Audio is local; this just
needs to ensure a daemon is running.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

Log = Callable[[str], None]


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
        subprocess.run(
            ["pulseaudio", "--start", "--exit-idle-time=-1"],
            check=True,
            capture_output=True,
            timeout=15,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if log:
            log(f"warning: pulseaudio failed to start: {exc}")
        return False
    return is_running()
