"""app/native/gpu.py: preset coherence, Adreno-only filtering, profile
persistence.

    python tests/test_gpu.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.native import gpu


def _with_temp_config(test):
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


def test_presets_are_coherent() -> None:
    names = [p.name for p in gpu.PRESETS]
    check(len(names) == len(set(names)), f"duplicate preset names: {names}")
    check("software" in names, "the software baseline is missing")
    for preset in gpu.PRESETS:
        check(gpu.preset_by_name(preset.name) is preset, f"{preset.name} not findable")
        exports = gpu.client_exports(preset)
        check(exports, f"{preset.name} exports nothing")
        for line in exports.splitlines():
            check(line.startswith("export "), f"{preset.name}: bad export line {line!r}")
    check(gpu.preset_by_name("nonexistent") is None, "an unknown preset name resolved to something")


def test_adreno_only_presets_are_flagged() -> None:
    for name in ("zink", "turnip"):
        preset = gpu.preset_by_name(name)
        check(preset is not None, f"{name} preset missing")
        check(preset.adreno_only, f"{name} should be marked adreno_only")
    software = gpu.preset_by_name("software")
    check(not software.adreno_only, "software must always be a candidate")


def test_candidates_excludes_adreno_only_on_mali() -> None:
    names = [p.name for p in gpu.candidates(vendor="mali")]
    check("zink" not in names, "zink offered on a non-Adreno device")
    check("turnip" not in names, "turnip offered on a non-Adreno device")
    check("software" in names, "software must survive every vendor filter")


def test_candidates_excludes_adreno_only_on_unknown_vendor() -> None:
    names = [p.name for p in gpu.candidates(vendor="unknown")]
    check("zink" not in names, "zink must not be assumed available on an unknown GPU")
    check("turnip" not in names, "turnip must not be assumed available on an unknown GPU")


def test_candidates_includes_adreno_only_on_adreno() -> None:
    names = [p.name for p in gpu.candidates(vendor="adreno")]
    check("zink" in names, "zink should be offered on Adreno")
    check("turnip" in names, "turnip should be offered on Adreno")


@_with_temp_config
def test_profile_round_trip() -> None:
    check(gpu.save_profile(gpu.PRESETS[0], 42), "could not save a measured profile")
    check(gpu.load_profile() is gpu.PRESETS[0], "profile did not round-trip")

    check(gpu.set_profile_manually(gpu.PRESETS[1]), "manual override reported failure")
    check(gpu.load_profile() is gpu.PRESETS[1], "manual override did not stick")


@_with_temp_config
def test_load_profile_defaults_to_software_when_unset() -> None:
    check(gpu.load_profile() is gpu.PRESETS[0], "should default to the software baseline")


TESTS = [
    test_presets_are_coherent,
    test_adreno_only_presets_are_flagged,
    test_candidates_excludes_adreno_only_on_mali,
    test_candidates_excludes_adreno_only_on_unknown_vendor,
    test_candidates_includes_adreno_only_on_adreno,
    test_profile_round_trip,
    test_load_profile_defaults_to_software_when_unset,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
