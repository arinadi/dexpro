"""app/native/x11.py: socket path construction and timeout behavior.

The real connect-success path needs a live X11 socket (Termux/device, or
the Docker dev container's XFCE session via docker/dev/dev.sh) — not
something a bare unit test can exercise.

    python tests/test_x11.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import x11


def test_socket_path_matches_display_number() -> None:
    path = x11.socket_path()
    check(path.endswith(f"X{x11._DISPLAY_NUM}"), f"unexpected socket path: {path}")
    check(".X11-unix" in path, f"socket path missing .X11-unix: {path}")


def test_wait_for_socket_times_out_when_absent() -> None:
    start = time.monotonic()
    result = x11.wait_for_socket(timeout=1.0, interval=0.2)
    elapsed = time.monotonic() - start
    check(result is False, "wait_for_socket should report failure when nothing is listening")
    check(elapsed < 3.0, f"wait_for_socket took too long to give up: {elapsed:.1f}s")


def test_start_fails_gracefully_when_binary_missing() -> None:
    # termux-x11 doesn't exist on this dev machine, and neither does pkg
    # — start() now attempts to auto-install it (2026-08-26, same fix
    # class as GPU Bench's missing glmark2) before giving up, but must
    # still return None and log, never raise.
    messages: list[str] = []
    proc = x11.start(log=messages.append)
    check(proc is None, "must not return a process when termux-x11 is unavailable")
    check(any("termux-x11" in m for m in messages), f"no reason logged, got {messages!r}")


def test_start_delegates_install_to_native_packages() -> None:
    # 2026-08-26: start() used to just log "termux-x11 not installed" and
    # give up — same fix class as GPU Bench's missing glmark2 / audio's
    # missing pulseaudio. Now it asks native.packages.ensure_binary() to
    # install the correct package (termux-x11-nightly, not "termux-x11").
    from unittest import mock

    calls = []
    with mock.patch(
        "app.native.x11.native_packages.ensure_binary",
        side_effect=lambda binary, package, log=None: calls.append((binary, package)) or False,
    ):
        proc = x11.start(log=lambda msg: None)
    check(proc is None, "must not attempt to launch when the mocked install reports failure")
    check(calls == [("termux-x11", "termux-x11-nightly")], f"got {calls!r}")


def test_launch_app_fails_gracefully_when_am_missing() -> None:
    # No `am` on this Windows dev machine — must fail gracefully to
    # False and log why, never raise.
    messages: list[str] = []
    result = x11.launch_app(log=messages.append)
    check(result is False, "must report failure gracefully when am is unavailable")
    check(any("Termux:X11 app" in m for m in messages), f"got {messages!r}")


def test_launch_app_starts_the_correct_activity() -> None:
    # Regression test for a real reported gap: start()/stop() only ever
    # touched the termux-x11 *server binary*, never the Termux:X11
    # *Android app* that actually shows the rendered surface — matching
    # XLabs' own start_x11(), which `am start`s the app right after the
    # server comes up.
    import subprocess
    from unittest import mock

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch.object(x11.subprocess, "run", side_effect=fake_run):
        result = x11.launch_app()
    check(result is True, "must report success when the mocked am start succeeds")
    check(calls == [["am", "start", "-n", x11.APP_ACTIVITY]], f"got {calls!r}")
    check(x11.APP_ACTIVITY == "com.termux.x11/com.termux.x11.MainActivity", x11.APP_ACTIVITY)


def test_stop_force_stops_the_app_as_well_as_the_server() -> None:
    import subprocess
    from unittest import mock

    kill_calls = []
    am_calls = []

    def fake_run(cmd, **kwargs):
        am_calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    with mock.patch.object(
        x11.proc, "kill_pattern", side_effect=lambda p, log=None: kill_calls.append(p) or True
    ):
        with mock.patch.object(x11.subprocess, "run", side_effect=fake_run):
            x11.stop()
    check(kill_calls == ["termux-x11"], f"got {kill_calls!r}")
    check(["am", "force-stop", x11.APP_PACKAGE] in am_calls, f"got {am_calls!r}")


def test_draw_path_flags_maps_each_option() -> None:
    check(x11.draw_path_flags("normal") == [], "normal should add no flags")
    check(x11.draw_path_flags(None) == [], "unset should default to normal (no flags)")
    check(x11.draw_path_flags("legacy-drawing") == ["-legacy-drawing"], "legacy-drawing mapping")
    check(x11.draw_path_flags("force-bgra") == ["-force-bgra"], "force-bgra mapping")
    combined = x11.draw_path_flags("legacy-drawing+force-bgra")
    check(combined == ["-legacy-drawing", "-force-bgra"], f"combined mapping wrong: {combined!r}")


def test_draw_path_flags_unknown_value_is_safe() -> None:
    check(x11.draw_path_flags("garbage") == [], "an unrecognized value must not raise or guess")


TESTS = [
    test_socket_path_matches_display_number,
    test_wait_for_socket_times_out_when_absent,
    test_start_fails_gracefully_when_binary_missing,
    test_start_delegates_install_to_native_packages,
    test_launch_app_fails_gracefully_when_am_missing,
    test_launch_app_starts_the_correct_activity,
    test_stop_force_stops_the_app_as_well_as_the_server,
    test_draw_path_flags_maps_each_option,
    test_draw_path_flags_unknown_value_is_safe,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
