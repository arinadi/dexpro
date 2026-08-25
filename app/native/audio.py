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
mechanism that consumes its dextop-audio toggle file — twice, 2026-08-25
and again 2026-08-26 specifically hunting for where pulseaudio actually
gets started. Confirmed dead end both times: none of dextop's own
scripts read the toggle or start pulseaudio based on it, and the shared
library dextop sources for its actual logic (`frobulator`, fetched from
its own CDN at runtime) isn't vendored in this checkout and isn't
available to inspect further. The live trigger is most likely
PulseAudio's own client-side autospawn or an XFCE-shipped autostart
.desktop entry, but that stays an educated guess, not a confirmed
finding. What IS confirmed from the README is the *default*: off,
opt-in only. dexpro matches that default rather than always attempting
to start PulseAudio unconditionally every session, which is the
behavior this was previously reported against.

test() (2026-08-26): ported from XLabs' audio.py — the actually useful
half of it, at least. XLabs tests four unix/tcp/shm methods because its
PulseAudio *client* runs inside a proot container and has to reach the
*host's* server across that boundary; dexpro has no such boundary, so
that whole multi-method dance doesn't apply (same reasoning as this
module's own top section). What's worth keeping is XLabs' core insight:
is_running()/ensure_server() only ever check that the *daemon process*
answers — never that a sink exists or that sound actually plays. A
"running" server with zero usable sinks reports exactly the same as a
working one. test() generates a real sine-wave tone (pure stdlib
wave/math/struct — ported near-verbatim from XLabs, which generates
rather than ships a file specifically to avoid bundling one for a single
beep) and plays it through paplay, so "audio works" means something was
actually verified, not assumed.
"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import wave
from collections.abc import Callable

from .. import config, const
from . import packages as native_packages

Log = Callable[[str], None]

ENABLED_KEY = "AUDIO_ENABLED"
TEST_TONE_NAME = "dexpro-test-tone.wav"


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
    if not native_packages.ensure_binary("pulseaudio", "pulseaudio", log):
        if log:
            log("warning: pulseaudio unavailable — session will run without audio")
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


# ── Test tone (ported from XLabs' audio.py test()) ────────────


def sinks() -> list[str]:
    """Output devices PulseAudio knows about. No sink means no sound,
    even with the daemon running — is_running() alone can't tell the
    two apart."""
    env = dict(os.environ, PULSE_AUTOSPAWN="0")
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True,
            timeout=10,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            return []
        return [line.split("\t")[1] for line in result.stdout.splitlines() if "\t" in line]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def write_test_tone(path: str, seconds: float = 1.0, hz: int = 440) -> bool:
    """Writes a short sine wave. Generated rather than shipped: the
    native session has no sound files of its own, and this avoids
    adding a package or bundling an asset for one beep."""
    rate = 16000
    try:
        with wave.open(path, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            frames = bytearray()
            for i in range(int(rate * seconds)):
                # Fade the last 10% so it ends without a click.
                progress = i / (rate * seconds)
                gain = 0.3 * (1.0 if progress < 0.9 else (1.0 - progress) * 10)
                sample = gain * 32767 * math.sin(2 * math.pi * hz * i / rate)
                frames += struct.pack("<h", int(sample))
            out.writeframes(bytes(frames))
        return True
    except (OSError, wave.Error):
        return False


def test(log: Log) -> bool:
    """Actually verifies audio works end to end, not just that the
    daemon process answers: confirms a sink exists, then plays a real
    tone through it and checks paplay's own exit code. dexpro has no
    proot boundary to test multiple methods across (unlike XLabs' four
    unix/tcp/shm methods) — this is the local half of XLabs' test(),
    the container-boundary half doesn't apply here."""
    if not is_enabled():
        log("audio is disabled in Settings — enable it first")
        return False

    if not ensure_server(log):
        log("[red]PulseAudio server isn't reachable — can't test playback.[/red]")
        return False

    available = sinks()
    log(f"sinks: {', '.join(available) if available else 'NONE — nothing can play'}")
    if not available:
        log("[red]No output sink — audio cannot play even though the server is up.[/red]")
        return False

    tone = os.path.join(const.TMPDIR, TEST_TONE_NAME)
    if not write_test_tone(tone):
        log("[red]Could not write the test tone.[/red]")
        return False
    log(f"tone: {tone}")

    if not native_packages.ensure_binary("paplay", "pulseaudio", log):
        log("[red]paplay not found — cannot test playback.[/red]")
        return False

    log("playing (you should hear a short tone)...")
    try:
        result = subprocess.run(["paplay", tone], capture_output=True, timeout=10, text=True)
    except subprocess.TimeoutExpired:
        log("[red]paplay timed out.[/red]")
        return False
    if result.returncode != 0:
        log(f"[red]paplay failed (exit {result.returncode}): {result.stderr.strip()}[/red]")
        return False
    log("[bold green]OK — playback succeeded.[/bold green]")
    return True
