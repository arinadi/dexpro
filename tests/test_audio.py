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


TESTS = [
    test_is_running_returns_a_bool,
    test_ensure_server_never_raises,
    test_is_enabled_defaults_to_off,
    test_set_enabled_round_trips,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
