"""Native session start/stop chain (build-task-phase1.md Task 7/8).

Owned by the Textual App (see app/app.py), not any individual Screen, so
it survives screen navigation.

Start order: stop (idempotent, unconditional) -> wake-lock -> storage
link -> audio.ensure_server -> GPU profile load -> start_x11 ->
wait_for_x11 -> start_session -> wait for xfce4-session to actually
come up.

Stop order: innermost first — session process, then X11, then audio,
then wake-unlock — verified with pgrep rather than just assumed,
matching XLabs' explicit "verifies with pgrep rather than just claiming
success" principle for Stop Desktop.

2026-08-26: `start()`/`stop()` gained an optional `log` parameter after a
real investigation (Firefox showing no sound) turned into a much bigger
finding — every message this class had ever logged went to `self.log`,
which app.py wires to Textual's own internal devtools log, NOT the
visible "Starting/Stopping dexpro session" ActionScreen the user is
actually watching. Every audio/x11/wakelock diagnostic added this whole
session was invisible there the entire time. Now the screen's own
logger is threaded through explicitly (matching every other fix() in
this codebase — Issue.fix(log), gpu.bench(log) — none of them rely on
an instance-level default either), and `self.log` only remains as the
App-level fallback for on_unmount()'s no-screen-available stop().

Also ported two things from XLabs' own start.py/stop_desktop() this
same investigation surfaced were missing here: stop() never killed
PulseAudio or cleaned up its runtime dir (a stale, dead-but-present
socket file was confirmed live — see native/audio.py's own docstring),
and start() never actually waited to confirm xfce4-session came up,
just fired the script and returned. XLabs' README explicitly documents
Android 12+'s phantom process killer as a known cause of a background
process (PulseAudio, or the session itself) dying on its own — see
_wait_for_session()'s failure message.

2026-08-26 (later same day): "polite kill doesn't work" — _kill()'s own
blanket `pkill -f pattern` sweep (for anything not directly tracked by
the Popen handle) was a single, unverified SIGTERM with no escalation,
same as x11.py's own kill call before it was fixed the same way. Now
uses native.proc.kill_pattern() (TERM, wait, confirm via pgrep, SIGKILL
if still alive). Also added a final `_sweep_survivors()` step at the end
of stop(), matching XLabs' stop_desktop()'s own last "anything that
outlived its parent" catch-all.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable

from .. import backup, config, const
from ..android import storage as android_storage
from . import audio, gpu, wakelock, x11
from . import proc as proc_util
from . import session as session_mod

_SESSION_STARTUP_TIMEOUT = 20.0

# A final catch-all sweep on Stop, matching XLabs' stop_desktop() step 4
# ("anything that outlived its parent") — xfwm4/xfdesktop are xfce4-
# session's own children and could in principle survive it; pulseaudio/
# virgl_test_server/termux-x11 are already handled by their own modules'
# stop paths above, but a belt-and-suspenders final check costs one
# cheap pgrep when there's nothing left to catch.
_SURVIVOR_PATTERN = (
    "xfce4-session|startxfce4|xfwm4|xfdesktop|termux-x11|virgl_test_server|pulseaudio"
)

STORAGE_LINK_KEY = "STORAGE_LINK"
# Re-researched from dextop 2026-08-26: its own setup always backs up the
# home directory before proceeding, "regardless, to ensure some kind of
# safety" (README). link_unified_home() *replaces* top-level home entries
# — the one genuinely destructive thing this module does — so it gets the
# same one-time safety net, gated so normal session starts don't create a
# fresh archive every single time.
UNIFIED_HOME_BACKUP_DONE_KEY = "UNIFIED_HOME_BACKUP_DONE"

Log = Callable[[str], None]


class SessionError(RuntimeError):
    pass


class Lifecycle:
    def __init__(self, log: Log | None = None) -> None:
        self.log: Log = log or (lambda _msg: None)
        self._x11_proc: subprocess.Popen | None = None
        self._session_proc: subprocess.Popen | None = None

    def start(self, log: Log | None = None) -> None:
        log = log or self.log
        self.stop(log)

        wakelock.acquire(log)
        self._link_storage(log)
        pulse_ok = self._ensure_audio(log)
        preset = gpu.load_profile()

        extra_flags = x11.draw_path_flags(config.get(x11.X11_FLAGS_KEY))
        self._x11_proc = x11.start(log, extra_flags=extra_flags)
        if self._x11_proc is None:
            raise SessionError("termux-x11 failed to launch")
        if not x11.wait_for_socket():
            raise SessionError("X11 socket never came up")

        # The server process alone renders nothing visible — the
        # Termux:X11 *Android app* is the actual window Android shows
        # the render surface in. x11.start() only ever launched the
        # server; this was missing entirely.
        log(f"$ am start -n {x11.APP_ACTIVITY}")
        x11.launch_app(log)

        script = session_mod.build_script(preset, pulse_ok)
        script_path = self._write_script(script)
        log(f"$ bash {script_path}")
        self._session_proc = subprocess.Popen(["bash", script_path])

        if not self._wait_for_session(log):
            raise SessionError(
                "xfce4-session did not stay up — if it started then vanished "
                "quickly, Android's phantom process killer (12+) is a common "
                "cause; Doctor can't fix that OS setting, but disabling it via "
                "adb (settings_enable_monitor_phantom_procs) or Developer "
                "Options is the documented workaround (same issue XLabs/"
                "dextop both hit)"
            )
        log("xfce4-session is up")

    def _wait_for_session(self, log: Log) -> bool:
        # Previously returned right after Popen-ing the script with zero
        # confirmation the session actually came up — "started" and
        # "silently never appeared" looked identical. Polls rather than a
        # fixed sleep since a cold start on a slow phone can take a while
        # (same reasoning as x11.wait_for_socket()).
        for waited in range(1, int(_SESSION_STARTUP_TIMEOUT) + 1):
            time.sleep(1)
            if self.is_running():
                log(f"  session up after {waited}s")
                return True
            if waited in (5, 10, 15):
                log(f"  still waiting ({waited}s)...")
        return False

    def _ensure_audio(self, log: Log) -> bool:
        # Off by default (audio.is_enabled()), matching dextop's own
        # documented default — "not recommended for use... process and
        # cycle intensive on the device's battery and processor(s)".
        # Previously always attempted every session; the on-device
        # report of PulseAudio "not running" was, in part, this doing
        # exactly that on a device where it doesn't work — now it's an
        # explicit, logged, opt-in choice instead of a silent default.
        if not audio.is_enabled():
            log("audio disabled in Settings (default off) — skipping pulseaudio")
            return False
        return audio.ensure_server(log)

    def _link_storage(self, log: Log) -> None:
        # Always-on, matching dextop's own default (populates
        # $PREFIX/media with /storage/self/primary + any labeled SD
        # cards/external mounts). Both fail gracefully to no-ops on a
        # platform with no /storage or no os.symlink privilege — safe to
        # call unconditionally, including on this Windows dev machine.
        android_storage.link_primary_storage(const.MEDIA_DIR, log)
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                mounts_text = f.read()
        except OSError:
            mounts_text = ""
        android_storage.link_external_storage(mounts_text, const.MEDIA_DIR, log)

        # Opt-in only (dextop's own default-off behavior for this mode) —
        # replaces top-level home entries with a "Home"-labeled mount's
        # contents, so it must never run unless the user explicitly asked.
        if config.get(STORAGE_LINK_KEY) == "unified-home":
            if self._ensure_unified_home_backup(log):
                android_storage.link_unified_home(const.MEDIA_DIR, const.TERMUX_HOME, log)
            else:
                log("skipping unified-home linking this session — backup didn't succeed")

    def _ensure_unified_home_backup(self, log: Log) -> bool:
        if config.get(UNIFIED_HOME_BACKUP_DONE_KEY):
            return True
        log(
            "unified home enabled for the first time — backing up the "
            "current home before replacing anything in it..."
        )
        archive = backup.backup_native_home(log=log)
        if archive is None:
            return False
        config.set_value(UNIFIED_HOME_BACKUP_DONE_KEY, "1")
        return True

    def stop(self, log: Log | None = None) -> None:
        log = log or self.log
        self._kill(self._session_proc, "xfce4-session", log)
        self._session_proc = None
        x11.stop(log)
        self._x11_proc = None
        audio.stop_server(log)
        self._clean_runtime_dir(log)
        wakelock.release(log)
        self._sweep_survivors(log)

    def _sweep_survivors(self, log: Log) -> None:
        if not proc_util.pgrep(_SURVIVOR_PATTERN):
            return
        log("sweeping survivors...")
        proc_util.kill_pattern(_SURVIVOR_PATTERN, log, wait=0.5)

    def _clean_runtime_dir(self, log: Log) -> None:
        # Matches XLabs' own stop_desktop() "cleaning sockets" step — a
        # stale-but-present pulse/native socket file (confirmed live: the
        # daemon was dead, the socket file wasn't) would otherwise sit
        # around and could confuse the next start.
        try:
            shutil.rmtree(const.XDG_RUNTIME_DIR, ignore_errors=True)
        except OSError as exc:
            log(f"warning: could not clean {const.XDG_RUNTIME_DIR}: {exc}")

    def is_running(self) -> bool:
        return self._session_proc is not None and self._session_proc.poll() is None

    def _write_script(self, content: str) -> str:
        os.makedirs(const.TMPDIR, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="dexpro-session-", suffix=".sh", dir=const.TMPDIR)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def _kill(self, proc: subprocess.Popen | None, pattern: str, log: Log | None = None) -> None:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        # native.proc.kill_pattern(), not a bare pkill: catches anything
        # not directly tracked by the Popen handle above (session.py's
        # script `exec`s into xfce4-session, so the tracked handle IS the
        # real process — but this sweep is the safety net if that ever
        # isn't true), verifies it actually died, and escalates to
        # SIGKILL if a plain TERM didn't work — "polite kill doesn't
        # work" was a real reported issue with this exact kind of
        # unverified pkill elsewhere in this codebase.
        proc_util.kill_pattern(pattern, log)
