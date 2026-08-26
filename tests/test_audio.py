"""app/native/audio.py: is_running()/ensure_server() contract when no
real PulseAudio daemon is reachable (true on this dev machine).

    python tests/test_audio.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.native import audio


def test_is_running_returns_a_bool() -> None:
    check(isinstance(audio.is_running(), bool), "is_running() must return a bool")


def test_ensure_server_never_raises() -> None:
    messages: list[str] = []
    result = audio.ensure_server(log=messages.append)
    check(isinstance(result, bool), "ensure_server() must return a bool, never raise")


def test_ensure_server_delegates_install_to_native_packages() -> None:
    # 2026-08-26: ensure_server() used to just warn "pulseaudio not
    # installed" and give up — same shape of bug as GPU Bench's missing
    # glmark2. Now it asks native.packages.ensure_binary() to install it.
    from unittest import mock

    calls = []
    with mock.patch(
        "app.native.audio.native_packages.ensure_binary",
        side_effect=lambda binary, package, log=None: calls.append((binary, package)) or False,
    ):
        result = audio.ensure_server(log=lambda msg: None)
    check(result is False, "must still fail gracefully when the mocked install reports failure")
    check(calls == [("pulseaudio", "pulseaudio")], f"got {calls!r}")


def _isolated_config(test):
    def wrapper():
        original = const.CONFIG_FILE
        fd, path = tempfile.mkstemp(suffix=".env")
        os.close(fd)
        os.remove(path)
        const.CONFIG_FILE = path
        try:
            test()
        finally:
            const.CONFIG_FILE = original
            if os.path.exists(path):
                os.remove(path)

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated_config
def test_is_enabled_defaults_to_off() -> None:
    # dextop's own documented default — "not recommended for use...
    # process and cycle intensive" — not dexpro's prior always-on
    # behavior.
    check(audio.is_enabled() is False, "audio must default to off, unconfigured")


@_isolated_config
def test_set_enabled_round_trips() -> None:
    audio.set_enabled(True)
    check(audio.is_enabled() is True, "set_enabled(True) must persist")
    audio.set_enabled(False)
    check(audio.is_enabled() is False, "set_enabled(False) must persist and clear the key")


def test_is_samsung_returns_false_without_getprop() -> None:
    # No getprop on this Windows dev machine — must fail gracefully to
    # False, not raise.
    check(audio._is_samsung() is False, "expected False when getprop is unavailable")


def test_ensure_server_preloads_libskcodec_on_samsung() -> None:
    # Community-confirmed workaround (r/termux): Samsung devices can need
    # LD_PRELOAD=/system/lib64/libskcodec.so before pulseaudio starts or
    # the daemon fails to initialize — gated to Samsung + the file
    # actually existing, so it can never affect any other device.
    import subprocess
    import unittest.mock as mock

    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:1] == ["pulseaudio"]:
            captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with mock.patch.object(audio, "is_running", return_value=False):
        with mock.patch.object(audio, "_is_samsung", return_value=True):
            with mock.patch.object(audio.os.path, "exists", return_value=True):
                with mock.patch.object(
                    audio.native_packages, "ensure_binary", return_value=True
                ):
                    with mock.patch.object(audio.os, "makedirs"):
                        with mock.patch.object(audio.os, "chmod"):
                            with mock.patch.object(audio.subprocess, "run", side_effect=fake_run):
                                audio.ensure_server(log=lambda _msg: None)
    check("env" in captured, "pulseaudio was never invoked")
    check(
        captured["env"].get("LD_PRELOAD") == audio._SAMSUNG_LD_PRELOAD,
        f"expected LD_PRELOAD set, got {captured['env'].get('LD_PRELOAD')!r}",
    )


def test_ensure_server_skips_preload_when_library_missing() -> None:
    import subprocess
    import unittest.mock as mock

    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:1] == ["pulseaudio"]:
            captured["env"] = kwargs.get("env")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with mock.patch.object(audio, "is_running", return_value=False):
        with mock.patch.object(audio, "_is_samsung", return_value=True):
            with mock.patch.object(audio.os.path, "exists", return_value=False):
                with mock.patch.object(
                    audio.native_packages, "ensure_binary", return_value=True
                ):
                    with mock.patch.object(audio.os, "makedirs"):
                        with mock.patch.object(audio.os, "chmod"):
                            with mock.patch.object(audio.subprocess, "run", side_effect=fake_run):
                                audio.ensure_server(log=lambda _msg: None)
    check("LD_PRELOAD" not in captured["env"], "must not set LD_PRELOAD when the file is absent")


def test_stop_server_is_a_noop_when_nothing_is_running() -> None:
    # No real pulseaudio on this Windows dev machine — is_running() is
    # already False, so stop_server() must return without raising and
    # without attempting a pointless --kill.
    audio.stop_server(log=lambda _msg: None)


def test_stop_server_kills_and_logs_when_running() -> None:
    # Matches XLabs' stop_desktop(): `pulseaudio --kill` is the clean
    # shutdown path, called whenever a daemon is actually up.
    from unittest import mock

    messages: list[str] = []
    calls = []

    def fake_run(cmd, **kwargs):
        import subprocess as sp

        calls.append(cmd)
        return sp.CompletedProcess(cmd, 0)

    # True once (the initial check), then False (it actually died, both
    # for the poll loop's own check and the final not-yet-dead check) —
    # exercises the real shutdown path without waiting out the real 5s
    # poll timeout below.
    with mock.patch.object(audio, "is_running", side_effect=[True, False, False]):
        with mock.patch.object(audio.subprocess, "run", side_effect=fake_run):
            audio.stop_server(log=messages.append)
    check(calls == [["pulseaudio", "--kill"]], f"got {calls!r}")
    check(any("pulseaudio --kill" in m for m in messages), f"got {messages!r}")


def test_stop_server_waits_for_the_daemon_to_actually_die() -> None:
    # Real bug found live: audio worked, then vanished after a Stop +
    # Start cycle. `pulseaudio --kill` doesn't block until the daemon
    # has actually exited — stop_server() must poll is_running() rather
    # than trusting the kill command returned, or the very next
    # ensure_server() call can see the OLD, dying instance as "still
    # running" and skip starting a fresh one.
    from unittest import mock

    with mock.patch.object(audio, "is_running", side_effect=[True, True, True, False, False]):
        with mock.patch.object(audio.subprocess, "run", return_value=None):
            with mock.patch.object(audio.time, "sleep"):
                audio.stop_server(log=lambda _msg: None)
    # No assertion needed beyond "this returns" — a version that just
    # trusted `pulseaudio --kill`'s return would never re-check
    # is_running() at all, so the mocked side_effect sequence above
    # (three Trues before the final False) would never be exhausted;
    # StopIteration would propagate here if that regressed.


def test_stop_server_logs_a_warning_if_it_never_actually_stops() -> None:
    from unittest import mock

    messages: list[str] = []
    # First monotonic() call sets the deadline; the second (the while
    # check) is already past it — exits the poll loop immediately
    # instead of really waiting out the full 5s.
    with mock.patch.object(audio, "is_running", return_value=True):
        with mock.patch.object(audio.subprocess, "run", return_value=None):
            with mock.patch.object(audio.time, "sleep"):
                with mock.patch.object(audio.time, "monotonic", side_effect=[0, 100]):
                    audio.stop_server(log=messages.append)
    check(
        any("did not stop" in m for m in messages),
        f"expected a warning when the daemon never actually stops, got {messages!r}",
    )


def test_pulse_env_pins_xdg_runtime_dir_to_the_shared_constant() -> None:
    # Regression test for a real reported bug: "Test sudah on dan bunyi
    # tapi di XFCE masih belum keluar suara" — every PulseAudio-facing
    # call here must agree with the XFCE session script on exactly the
    # same XDG_RUNTIME_DIR, or the two independently guess and disagree.
    env = audio._pulse_env()
    check(
        env["XDG_RUNTIME_DIR"] == const.XDG_RUNTIME_DIR,
        f"expected the shared constant, got {env['XDG_RUNTIME_DIR']!r}",
    )


def test_sinks_returns_empty_list_when_pactl_missing() -> None:
    # No pactl on this Windows dev machine — must fail gracefully to
    # "no sinks", not raise.
    check(audio.sinks() == [], "expected an empty list when pactl is unavailable")


def test_write_test_tone_produces_a_real_wav_file() -> None:
    # Pure stdlib (wave/math/struct) — this genuinely works without any
    # real audio hardware, so it's tested for real, not just "doesn't
    # crash".
    import wave

    tmp = tempfile.mkdtemp(prefix="dexpro-audio-test-")
    path = os.path.join(tmp, "tone.wav")
    try:
        ok = audio.write_test_tone(path, seconds=0.1)
        check(ok, "write_test_tone should succeed with pure-stdlib wave/math/struct")
        check(os.path.exists(path), "the wav file must actually exist")
        with wave.open(path, "rb") as f:
            check(f.getnchannels() == 1, "expected mono")
            check(f.getframerate() == 16000, "expected the documented sample rate")
            check(f.getnframes() > 0, "expected non-empty audio frames")
    finally:
        os.remove(path)
        os.rmdir(tmp)


@_isolated_config
def test_test_reports_disabled_when_audio_off() -> None:
    messages: list[str] = []
    result = audio.test(log=messages.append)
    check(result is False, "test() must refuse to run when audio is disabled")
    check(any("disabled in Settings" in m for m in messages), f"got {messages!r}")


@_isolated_config
def test_test_never_raises_when_enabled_but_no_real_audio() -> None:
    # No real pulseaudio/paplay on this dev machine — the whole point of
    # this test is that test() fails gracefully through every stage
    # rather than raising partway through.
    audio.set_enabled(True)
    messages: list[str] = []
    result = audio.test(log=messages.append)
    check(isinstance(result, bool), "must return a definite bool, never raise")
    check(result is False, "cannot actually succeed without real audio hardware")


TESTS = [
    test_is_running_returns_a_bool,
    test_ensure_server_never_raises,
    test_ensure_server_delegates_install_to_native_packages,
    test_is_samsung_returns_false_without_getprop,
    test_ensure_server_preloads_libskcodec_on_samsung,
    test_ensure_server_skips_preload_when_library_missing,
    test_stop_server_is_a_noop_when_nothing_is_running,
    test_stop_server_kills_and_logs_when_running,
    test_stop_server_waits_for_the_daemon_to_actually_die,
    test_stop_server_logs_a_warning_if_it_never_actually_stops,
    test_pulse_env_pins_xdg_runtime_dir_to_the_shared_constant,
    test_is_enabled_defaults_to_off,
    test_set_enabled_round_trips,
    test_sinks_returns_empty_list_when_pactl_missing,
    test_write_test_tone_produces_a_real_wav_file,
    test_test_reports_disabled_when_audio_off,
    test_test_never_raises_when_enabled_but_no_real_audio,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
