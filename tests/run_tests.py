#!/usr/bin/env python3
"""Run every dexpro test module together.

Tests are split by module (test_gpu.py, test_session.py, ...) — see
tests/support.py for the shared check()/run() helpers. This file just
collects each module's TESTS list and runs them as one suite.

    python tests/run_tests.py           # everything
    python tests/test_gpu.py            # just one module, while working on it
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import support
from test_audio import TESTS as AUDIO_TESTS
from test_config import TESTS as CONFIG_TESTS
from test_gpu import TESTS as GPU_TESTS
from test_main_screen import TESTS as MAIN_SCREEN_TESTS
from test_session import TESTS as SESSION_TESTS
from test_wakelock import TESTS as WAKELOCK_TESTS
from test_x11 import TESTS as X11_TESTS

# Low-level helpers first, TUI last — not load-bearing, just easier to
# read a failed run top to bottom.
ALL_TESTS = [
    *CONFIG_TESTS,
    *WAKELOCK_TESTS,
    *AUDIO_TESTS,
    *GPU_TESTS,
    *X11_TESTS,
    *SESSION_TESTS,
    *MAIN_SCREEN_TESTS,
]


def main() -> int:
    return support.run(ALL_TESTS)


if __name__ == "__main__":
    sys.exit(main())
