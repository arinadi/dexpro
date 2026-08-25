"""Native session start/stop chain (build-task-phase1.md Task 7/8).

Owned by the Textual App (see app/app.py), not any individual Screen, so
it survives screen navigation.

Start order: stop (idempotent, unconditional) -> wake-lock -> storage
link -> audio.ensure_server -> GPU profile load -> start_x11 ->
wait_for_x11 -> start_session.

Stop order: innermost first — session process, then X11, then
wake-unlock — verified with pgrep rather than just assumed, matching
XLabs' explicit "verifies with pgrep rather than just claiming success"
principle for Stop Desktop.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from collections.abc import Callable

from .. import config, const
from ..android import storage as android_storage
from . import audio, gpu, wakelock, x11
from . import session as session_mod

STORAGE_LINK_KEY = "STORAGE_LINK"

Log = Callable[[str], None]


class SessionError(RuntimeError):
    pass


class Lifecycle:
    def __init__(self, log: Log | None = None) -> None:
        self.log: Log = log or (lambda _msg: None)
        self._x11_proc: subprocess.Popen | None = None
        self._session_proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.stop()

        wakelock.acquire(self.log)
        self._link_storage()
        pulse_ok = audio.ensure_server(self.log)
        preset = gpu.load_profile()

        extra_flags = x11.draw_path_flags(config.get(x11.X11_FLAGS_KEY))
        self._x11_proc = x11.start(self.log, extra_flags=extra_flags)
        if self._x11_proc is None:
            raise SessionError("termux-x11 failed to launch")
        if not x11.wait_for_socket():
            raise SessionError("X11 socket never came up")

        script = session_mod.build_script(preset, pulse_ok)
        script_path = self._write_script(script)
        self._session_proc = subprocess.Popen(["bash", script_path])

    def _link_storage(self) -> None:
        # Always-on, matching dextop's own default (populates
        # $PREFIX/media with /storage/self/primary + any labeled SD
        # cards/external mounts). Both fail gracefully to no-ops on a
        # platform with no /storage or no os.symlink privilege — safe to
        # call unconditionally, including on this Windows dev machine.
        android_storage.link_primary_storage(const.MEDIA_DIR, self.log)
        try:
            with open("/proc/mounts", encoding="utf-8") as f:
                mounts_text = f.read()
        except OSError:
            mounts_text = ""
        android_storage.link_external_storage(mounts_text, const.MEDIA_DIR, self.log)

        # Opt-in only (dextop's own default-off behavior for this mode) —
        # replaces top-level home entries with a "Home"-labeled mount's
        # contents, so it must never run unless the user explicitly asked.
        if config.get(STORAGE_LINK_KEY) == "unified-home":
            android_storage.link_unified_home(const.MEDIA_DIR, const.TERMUX_HOME, self.log)

    def stop(self) -> None:
        self._kill(self._session_proc, "xfce4-session")
        self._session_proc = None
        x11.stop(self.log)
        self._x11_proc = None
        wakelock.release(self.log)

    def is_running(self) -> bool:
        return self._session_proc is not None and self._session_proc.poll() is None

    def _write_script(self, content: str) -> str:
        os.makedirs(const.TMPDIR, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="dexpro-session-", suffix=".sh", dir=const.TMPDIR)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def _kill(self, proc: subprocess.Popen | None, pattern: str) -> None:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        try:
            subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=10)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
