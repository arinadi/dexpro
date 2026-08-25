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
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from .. import config

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


def candidates(vendor: str | None = None) -> list[Preset]:
    if vendor is None:
        vendor = detect_vendor()
    result = []
    for preset in PRESETS:
        if preset.adreno_only and vendor != "adreno":
            continue
        if preset.requires and any(shutil.which(binary) is None for binary in preset.requires):
            continue
        result.append(preset)
    return result


# --- Benchmark ---

_SCORE_RE = re.compile(r"glmark2 Score:\s*(\d+)")


def run_glmark2(preset: Preset) -> int | None:
    """Runs glmark2 with the preset's env, returns the score, or None if
    it couldn't run (glmark2 missing, or the run failed/timed out)."""
    if shutil.which("glmark2") is None:
        return None

    env = dict(os.environ)
    env.update(preset.env)
    args = ["glmark2"]
    for scene in GLMARK2_SCENES:
        args += ["-b", f"{scene}:duration={GLMARK2_SECONDS_PER_SCENE}"]

    try:
        result = subprocess.run(
            args,
            env=env,
            capture_output=True,
            timeout=(GLMARK2_SECONDS_PER_SCENE * len(GLMARK2_SCENES)) + 15,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return None
    match = _SCORE_RE.search(result.stdout)
    return int(match.group(1)) if match else None


def bench(log: Log | None = None) -> tuple[Preset, int] | None:
    best: tuple[Preset, int] | None = None
    for preset in candidates():
        if log:
            log(f"benchmarking {preset.name}...")
        score = run_glmark2(preset)
        if score is None:
            continue
        if best is None or score > best[1]:
            best = (preset, score)
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
