"""app/native/audio.py: is_running()/ensure_server() contract when no
real PulseAudio daemon is reachable (true on this dev machine).

    python tests/test_audio.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import audio


def test_is_running_returns_a_bool() -> None:
    check(isinstance(audio.is_running(), bool), "is_running() must return a bool")


def test_ensure_server_never_raises() -> None:
    messages: list[str] = []
    result = audio.ensure_server(log=messages.append)
    check(isinstance(result, bool), "ensure_server() must return a bool, never raise")


TESTS = [
    test_is_running_returns_a_bool,
    test_ensure_server_never_raises,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
