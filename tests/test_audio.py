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
    test_is_enabled_defaults_to_off,
    test_set_enabled_round_trips,
    test_sinks_returns_empty_list_when_pactl_missing,
    test_write_test_tone_produces_a_real_wav_file,
    test_test_reports_disabled_when_audio_off,
    test_test_never_raises_when_enabled_but_no_real_audio,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
