"""app/native/gpu.py: preset coherence, Adreno-only filtering, profile
persistence.

    python tests/test_gpu.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

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


def test_run_glmark2_reports_when_glmark2_missing_and_pkg_unavailable() -> None:
    # Real, unmocked behavior on this dev machine: no glmark2, no pkg.
    # This is the exact bug reported live — "no candidate preset
    # produced a score" with zero explanation — now must explain why.
    messages: list[str] = []
    score = gpu.run_glmark2(gpu.PRESETS[0], log=messages.append)
    check(score is None, "must fail gracefully with no glmark2/pkg present")
    check(
        any("glmark2" in m for m in messages),
        f"expected a reason logged, got {messages!r}",
    )


def test_ensure_binary_delegates_to_native_packages_with_mapped_name() -> None:
    # gpu.py no longer implements its own install logic — it delegates to
    # native.packages.ensure_binary() (shared across every module with the
    # same "silently degrades if a binary is missing" shape), passing the
    # preset-specific binary->package mapping through.
    calls = []
    with mock.patch.object(
        gpu.native_packages,
        "ensure_binary",
        side_effect=lambda binary, package, log, attempted: calls.append((binary, package)) or True,
    ):
        ok = gpu._ensure_binary("virgl_test_server_android", None)
    check(ok is True, "must return whatever native_packages.ensure_binary reports")
    check(
        calls == [("virgl_test_server_android", "virglrenderer-android")],
        f"expected the mapped package name passed through, got {calls!r}",
    )


def test_run_glmark2_checks_termux_x11_is_running() -> None:
    # glmark2 "available" (mocked at the delegation boundary) but
    # termux-x11's socket doesn't exist on this dev machine — must refuse
    # with a clear reason, not attempt to launch glmark2 with no display.
    messages: list[str] = []
    with mock.patch.object(gpu.native_packages, "ensure_binary", return_value=True):
        score = gpu.run_glmark2(gpu.PRESETS[0], log=messages.append)
    check(score is None, "must not run without an active termux-x11 display")
    check(
        any("termux-x11 is not running" in m for m in messages),
        f"expected the display-not-running reason logged, got {messages!r}",
    )


def test_bench_reports_no_candidate_summary() -> None:
    messages: list[str] = []
    result = gpu.bench(log=messages.append)
    check(result is None, "cannot actually benchmark without real glmark2/pkg")
    check(
        any("No candidate preset produced a score" in m for m in messages),
        f"expected the summary line, got {messages!r}",
    )


TESTS = [
    test_presets_are_coherent,
    test_adreno_only_presets_are_flagged,
    test_candidates_excludes_adreno_only_on_mali,
    test_candidates_excludes_adreno_only_on_unknown_vendor,
    test_candidates_includes_adreno_only_on_adreno,
    test_profile_round_trip,
    test_load_profile_defaults_to_software_when_unset,
    test_run_glmark2_reports_when_glmark2_missing_and_pkg_unavailable,
    test_ensure_binary_delegates_to_native_packages_with_mapped_name,
    test_run_glmark2_checks_termux_x11_is_running,
    test_bench_reports_no_candidate_summary,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
