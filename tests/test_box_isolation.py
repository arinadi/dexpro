"""app/box/isolation.py: per-container proot isolation presets.

    python tests/test_box_isolation.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.box import isolation, manager


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


def test_preset_by_name_finds_known_presets() -> None:
    check(isolation.preset_by_name("isolated") is not None, "isolated should be a known preset")
    check(isolation.preset_by_name("nope") is None, "an unknown name should resolve to None")


@_isolated_config
def test_load_preset_defaults_to_full_access() -> None:
    preset = isolation.load_preset("work")
    default_msg = "an unconfigured container must default to full access"
    check(preset is isolation.DEFAULT_PRESET, default_msg)
    check(preset.flags == (), "the default preset must add no extra proot flags")


@_isolated_config
def test_save_preset_round_trips_and_is_per_container() -> None:
    isolated = isolation.preset_by_name("isolated")
    isolation.save_preset("work", isolated, 1234.0)

    check(isolation.load_preset("work") == isolated, "the saved preset must round-trip")
    other = isolation.load_preset("other-container")
    check(other is isolation.DEFAULT_PRESET, "a different container must not inherit work's preset")


@_isolated_config
def test_set_preset_manually_clears_the_score() -> None:
    from app import config

    isolated = isolation.preset_by_name("isolated")
    isolation.save_preset("work", isolated, 1234.0)
    check(config.get(isolation._score_key("work")) is not None, "sanity: score was saved")

    isolation.set_preset_manually("work", isolated)
    cleared_msg = "a manual pick must clear a stale score"
    check(config.get(isolation._score_key("work")) is None, cleared_msg)


@_isolated_config
def test_login_command_applies_the_saved_preset_by_default() -> None:
    isolated = isolation.preset_by_name("isolated")
    isolation.save_preset("work", isolated, 1234.0)

    args = manager.login_command("work")
    check("--isolated" in args, f"expected the saved preset's flags in {args!r}")


@_isolated_config
def test_login_command_isolation_preset_overrides_the_saved_one() -> None:
    # iobench.py's own use case: testing a candidate preset that isn't
    # (yet, or ever) the one saved for this container.
    isolation.save_preset("work", isolation.preset_by_name("isolated"), 1234.0)

    args = manager.login_command("work", isolation_preset=isolation.DEFAULT_PRESET)
    check("--isolated" not in args, f"explicit override must win over the saved preset: {args!r}")


TESTS = [
    test_preset_by_name_finds_known_presets,
    test_load_preset_defaults_to_full_access,
    test_save_preset_round_trips_and_is_per_container,
    test_set_preset_manually_clears_the_score,
    test_login_command_applies_the_saved_preset_by_default,
    test_login_command_isolation_preset_overrides_the_saved_one,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
