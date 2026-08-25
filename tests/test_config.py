"""app/config.py: KEY=value round-trip.

    python tests/test_config.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import config, const


def _with_temp_config(test):
    def wrapper():
        original = const.CONFIG_FILE
        fd, path = tempfile.mkstemp(suffix=".env")
        os.close(fd)
        os.remove(path)  # config.py must create it fresh, not assume it exists
        const.CONFIG_FILE = path
        try:
            test()
        finally:
            const.CONFIG_FILE = original
            if os.path.exists(path):
                os.remove(path)

    wrapper.__name__ = test.__name__
    return wrapper


@_with_temp_config
def test_config_round_trip() -> None:
    check(config.get("MISSING") is None, "missing key should be None")
    config.set_value("GPU_PROFILE", "virgl")
    check(config.get("GPU_PROFILE") == "virgl", "value did not round-trip")
    config.set_value("GPU_PROFILE", "zink")
    check(config.get("GPU_PROFILE") == "zink", "overwrite did not stick")
    config.unset("GPU_PROFILE")
    check(config.get("GPU_PROFILE") is None, "unset did not remove the key")


@_with_temp_config
def test_config_strips_quotes() -> None:
    with open(const.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write('KEY="quoted value"\n')
    check(config.get("KEY") == "quoted value", "quotes were not stripped on read")


@_with_temp_config
def test_config_ignores_comments_and_blank_lines() -> None:
    with open(const.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("# a comment\n\nGPU_PROFILE=virgl\n")
    values = config.load()
    check(values == {"GPU_PROFILE": "virgl"}, f"unexpected parse: {values!r}")


TESTS = [
    test_config_round_trip,
    test_config_strips_quotes,
    test_config_ignores_comments_and_blank_lines,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
