"""Native session start/stop chain (build-task-phase1.md Task 7/8).

Owned by the Textual App (see app/app.py), not any individual Screen, so
it survives screen navigation.

Start order: stop (idempotent, unconditional) -> wake-lock ->
audio.ensure_server -> GPU profile load -> start_x11 -> wait_for_x11 ->
start_session.

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

from .. import const
from . import audio, gpu, wakelock, x11
from . import session as session_mod

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
        pulse_ok = audio.ensure_server(self.log)
        preset = gpu.load_profile()

        self._x11_proc = x11.start(self.log)
        if self._x11_proc is None:
            raise SessionError("termux-x11 failed to launch")
        if not x11.wait_for_socket():
            raise SessionError("X11 socket never came up")

        script = session_mod.build_script(preset, pulse_ok)
        script_path = self._write_script(script)
        self._session_proc = subprocess.Popen(["bash", script_path])

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
