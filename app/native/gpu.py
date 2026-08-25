"""GPU renderer selection for the native session — "measure, don't guess",
XLabs' bench.py/isolation.py methodology.

Candidate list updated from XLabs' original virgl/ANGLE/zink/software set
per 2025/2026 termux-x11 hardware-acceleration docs (build-task-phase1.md
Task 4): no Android ANGLE integration was found (dropped); zink and
turnip are Adreno-only; freedreno/kgsl is experimental and reported to
break XFCE, so it is not offered as an auto-bench candidate at all.

NOTE: run_glmark2()'s exact CLI invocation (``-b scene:duration=N``) and
output parsing (``glmark2 Score: N``) are based on glmark2's general
documented usage, not verified against actual on-device output — treat
as a spike to confirm on the real device or in the Docker dev container,
per build-task-phase1.md's spike list.

2026-08-26: a real device report of "no candidate preset produced a
score" with no other detail turned up three actual gaps, found by
diffing against XLabs' installer/bench.py (which runs the same benchmark
inside a proot container rather than natively, but hits the same
X-display and missing-binary requirements): (1) glmark2 was never
installed anywhere in this codebase — every run silently hit "binary
missing" and returned None with zero explanation; (2) unlike XLabs'
explicit ``export DISPLAY=:0`` before invoking glmark2, run_glmark2()
only ever inherited whatever DISPLAY happened to already be in the
process environment — now explicitly set to x11.DISPLAY (":1" here,
XLabs' container uses ":0"); (3) XLabs checks termux-x11 is actually
running before benchmarking at all ("glmark2 renders off-screen but
still needs an X display for its context") — run_glmark2() had no such
guard. All three fixed, plus every failure path (missing binary,
termux-x11 down, timeout, nonzero exit with no score match) now logs why
instead of silently returning None. Missing binaries (glmark2 itself,
and virgl_test_server_android for the virgl preset) are now installed
on demand via ``pkg install -y <package>`` rather than assumed present —
_ensure_binary() always re-checks with shutil.which afterward rather
than trusting the install command's exit code alone.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from .. import config
from . import packages as native_packages
from . import x11

Log = Callable[[str], None]

PROFILE_KEY = "GPU_PROFILE"
SCORE_KEY = "GPU_SCORE"

GLMARK2_SCENES = ("build", "texture", "shading")
GLMARK2_SECONDS_PER_SCENE = 2.0


@dataclass(frozen=True)
class Preset:
    name: str
    env: dict[str, str]
    adreno_only: bool = False
    requires: tuple[str, ...] = ()  # binaries that must exist for this preset to be viable


PRESETS: tuple[Preset, ...] = (
    Preset(name="software", env={"LIBGL_ALWAYS_SOFTWARE": "1"}),
    Preset(
        name="virgl",
        env={"GALLIUM_DRIVER": "virpipe"},
        requires=("virgl_test_server_android",),
    ),
    Preset(
        name="zink",
        env={
            "GALLIUM_DRIVER": "zink",
            "MESA_GL_VERSION_OVERRIDE": "4.3COMPAT",
            "MESA_GLES_VERSION_OVERRIDE": "3.2",
            "ZINK_DESCRIPTORS": "lazy",
        },
        adreno_only=True,
    ),
    Preset(
        name="turnip",
        env={"MESA_LOADER_DRIVER_OVERRIDE": "zink", "TU_DEBUG": "noconform"},
        adreno_only=True,
    ),
)


def preset_by_name(name: str) -> Preset | None:
    for preset in PRESETS:
        if preset.name == name:
            return preset
    return None


def client_exports(preset: Preset) -> str:
    return "\n".join(f"export {key}={value}" for key, value in preset.env.items())


# --- GPU vendor detection (best-effort spike — see build-task-phase1.md) ---

_ADRENO_HINTS = ("adreno", "qcom", "kryo", "snapdragon")
_MALI_HINTS = ("mali", "exynos", "samsungexynos")


def detect_vendor(log: Log | None = None) -> str:
    """Returns "adreno", "mali", or "unknown".

    Best-effort — no single confirmed getprop key exists for this (see
    the Phase 1 spike table); tries several plausible ones.
    """
    for prop in ("ro.hardware", "ro.board.platform", "ro.chipname", "ro.product.board"):
        value = _getprop(prop)
        if not value:
            continue
        lowered = value.lower()
        if any(hint in lowered for hint in _ADRENO_HINTS):
            return "adreno"
        if any(hint in lowered for hint in _MALI_HINTS):
            return "mali"
    if log:
        log(
            "warning: could not determine GPU vendor — Adreno-only "
            "renderers (zink, turnip) will be skipped"
        )
    return "unknown"


def _getprop(prop: str) -> str | None:
    if shutil.which("getprop") is None:
        return None
    try:
        result = subprocess.run(
            ["getprop", prop], capture_output=True, timeout=5, text=True
        )
        value = result.stdout.strip()
        return value or None
    except subprocess.TimeoutExpired:
        return None


def _presets_for_vendor(vendor: str | None = None) -> list[Preset]:
    if vendor is None:
        vendor = detect_vendor()
    return [p for p in PRESETS if not (p.adreno_only and vendor != "adreno")]


def candidates(vendor: str | None = None) -> list[Preset]:
    """Presets viable right now without installing anything — a pure,
    no-side-effect query. bench() itself uses _presets_for_vendor() and
    _ensure_binary() instead, so a missing `requires` binary gets an
    install attempt rather than a silent skip."""
    result = []
    for preset in _presets_for_vendor(vendor):
        if preset.requires and any(shutil.which(binary) is None for binary in preset.requires):
            continue
        result.append(preset)
    return result


# --- Benchmark ---

_SCORE_RE = re.compile(r"glmark2 Score:\s*(\d+)")

# Termux package that provides each binary a preset depends on — needed
# because the binary name and the pkg name aren't always the same
# (virgl_test_server_android ships in the virglrenderer-android package).
_BINARY_PACKAGES: dict[str, str] = {
    "glmark2": "glmark2",
    "virgl_test_server_android": "virglrenderer-android",
}


def _ensure_binary(binary: str, log: Log | None, _attempted: set[str] | None = None) -> bool:
    return native_packages.ensure_binary(
        binary, _BINARY_PACKAGES.get(binary, binary), log, _attempted
    )


def run_glmark2(
    preset: Preset, log: Log | None = None, _attempted: set[str] | None = None
) -> int | None:
    """Runs glmark2 with the preset's env, returns the score, or None if
    it couldn't run — every failure path logs why (missing binary,
    termux-x11 not running, timeout, or a nonzero exit with no score in
    its output), instead of a bare None that reads as "nothing happened."
    """
    if not _ensure_binary("glmark2", log, _attempted):
        return None

    if not os.path.exists(x11.socket_path()):
        if log:
            log(
                "termux-x11 is not running — glmark2 renders off-screen but "
                "still needs an active X display. Start Desktop first, then "
                "bench again."
            )
        return None

    env = dict(os.environ)
    env["DISPLAY"] = x11.DISPLAY
    env.update(preset.env)
    args = ["glmark2", "--off-screen"]
    for scene in GLMARK2_SCENES:
        args += ["-b", f"{scene}:duration={GLMARK2_SECONDS_PER_SCENE}"]

    if log:
        log("$ " + " ".join(args))
    try:
        result = subprocess.run(
            args,
            env=env,
            capture_output=True,
            timeout=(GLMARK2_SECONDS_PER_SCENE * len(GLMARK2_SCENES)) + 15,
            text=True,
        )
    except subprocess.TimeoutExpired:
        if log:
            log(f"{preset.name}: timed out")
        return None

    match = _SCORE_RE.search(result.stdout)
    if match:
        return int(match.group(1))

    if log:
        log(f"{preset.name}: no score (exit {result.returncode})")
        tail = (result.stdout + result.stderr).strip().splitlines()[-5:]
        for line in tail:
            log(f"    {line}")
    return None


def bench(log: Log | None = None) -> tuple[Preset, int] | None:
    best: tuple[Preset, int] | None = None
    attempted: set[str] = set()
    for preset in _presets_for_vendor():
        if preset.requires and not all(
            _ensure_binary(b, log, attempted) for b in preset.requires
        ):
            if log:
                log(f"{preset.name}: skipped — required binary unavailable")
            continue
        if log:
            log(f"benchmarking {preset.name}...")
        score = run_glmark2(preset, log, attempted)
        if score is None:
            continue
        if log:
            log(f"{preset.name}: score {score}")
        if best is None or score > best[1]:
            best = (preset, score)
    if best is None and log:
        log("No candidate preset produced a score — see the log above for why.")
    return best


def save_profile(preset: Preset, score: int) -> bool:
    config.set_value(PROFILE_KEY, preset.name)
    config.set_value(SCORE_KEY, str(score))
    return True


def set_profile_manually(preset: Preset) -> bool:
    config.set_value(PROFILE_KEY, preset.name)
    config.unset(SCORE_KEY)
    return True


def load_profile() -> Preset:
    name = config.get(PROFILE_KEY)
    preset = preset_by_name(name) if name else None
    return preset or PRESETS[0]  # software is always a safe fallback
