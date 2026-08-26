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

2026-08-26 (later same day): the fixes above got glmark2 actually
installed and running for real, but every preset then failed with
"Error: main: Could not initialize canvas" — this update's own
``--off-screen`` flag (copied from XLabs' bench.py, which runs inside a
full proot-distro Debian/Mesa install) was the cause. Community reports
against termux-x11 specifically (termux/termux-packages#16763; a working
Adreno/Mali run posted there) confirm the actual working invocation is a
plain *onscreen* window — ``DISPLAY=:1 GALLIUM_DRIVER=virpipe glmark2``,
no ``--off-screen`` — so it was dropped. termux-x11's Mesa/virgl stack
apparently doesn't support the off-screen EGL surface path the way a
full desktop Mesa install does; XLabs' own container is a different
enough environment that this specific flag didn't carry over correctly.

2026-08-26 (later still): with --off-screen gone, "software" scored for
real, but "virgl" failed with "lost connection to rendering server on 8
read -1 22" — glmark2's virgl client speaks its protocol over a socket
to a *separate* renderer process (virgl_test_server_android), which
nothing here ever launched. Checking the binary merely *exists*
(candidates()/_ensure_binary, already in place) is not the same as it
being *running*. Added Preset.server + _start_renderer()/_stop_renderer()
(Popen the renderer, wait, confirm via pgrep, always pkill it in a
`finally` after the client runs) — ported from XLabs' own
_start_renderer(), which does exactly this for the same reason.

2026-08-26 (later still): user shared LinuxDroidMaster/Termux-Desktops'
own HardwareAcceleration.md — real, community-tested glmark2 scores for
both proot AND native Termux specifically. Cross-checking it against
this module's PRESETS surfaced real mismatches, not guesses:
- The "virgl" preset (bare ``virgl_test_server_android`` server,
  ``GALLIUM_DRIVER=virpipe`` client) is exactly the combination that
  doc's own native-Termux testing scored "Error" on every single run
  (5/5) — not a flaky failure, a consistently broken combination on
  native Termux specifically (their proot table shows the same
  combination *does* work there, 70-77). The combination that actually
  scores (92-93, their "VIRGL ZINK" row) uses a *different* server
  binary — ``virgl_test_server`` (from package virglrenderer-mesa-zink,
  confirmed via termux-user-repository/tur, not virglrenderer-android)
  started with zink-flavored server env — with the *same* virpipe client
  command, now also carrying the previously-missing
  ``MESA_GL_VERSION_OVERRIDE=4.0``. Preset gained `server_args`/
  `server_env` (server-side CLI flags/env, distinct from the client's
  own `env`) to express this.
- The "zink" preset's env was actually the *server*-side zink flavor
  from the combination above, mistakenly applied as this preset's own
  *client* env. Corrected to the doc's own direct, no-server zink client
  command (``GALLIUM_DRIVER=zink MESA_GL_VERSION_OVERRIDE=4.0``), which
  the doc's own native-Termux results score highest of every non-Turnip
  option (121-124).
- "turnip" dropped ``TU_DEBUG=noconform``: the doc lists that flag only
  for the *proot* Turnip invocation; its separate native-Termux Turnip
  section uses just ``MESA_LOADER_DRIVER_OVERRIDE=zink``.
- install.py's package list was missing ``mesa-zink``,
  ``virglrenderer-mesa-zink``, ``vulkan-loader-android`` (all four
  packages the doc says are needed together for native Termux hardware
  acceleration) and ``mesa-vulkan-icd-freedreno-dri3`` (Turnip) —added.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

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
    # A renderer binary to launch as a background process before the GL
    # client (glmark2) runs, or None if the client talks to the GPU
    # directly. virgl speaks its protocol over a socket to a *separate*
    # process — glmark2 alone was never going to find anything to
    # connect to.
    server: str | None = None
    server_args: tuple[str, ...] = ()
    server_env: dict[str, str] = field(default_factory=dict)


PRESETS: tuple[Preset, ...] = (
    Preset(name="software", env={"LIBGL_ALWAYS_SOFTWARE": "1"}),
    Preset(
        name="virgl",
        # Confirmed via LinuxDroidMaster/Termux-Desktops' own native-Termux
        # glmark2 results: a bare virgl_test_server_android server scored
        # "Error" on every single run (5/5) — this preset used to be exactly
        # that combination. The one that actually works natively (92-93,
        # their "VIRGL ZINK" row) uses a *different* server binary
        # (virgl_test_server, from the virglrenderer-mesa-zink package, not
        # virgl_test_server_android) started with zink-flavored server env —
        # the client command is unchanged (GALLIUM_DRIVER=virpipe). Also
        # adds MESA_GL_VERSION_OVERRIDE=4.0 to the client env, missing
        # before.
        env={"GALLIUM_DRIVER": "virpipe", "MESA_GL_VERSION_OVERRIDE": "4.0"},
        requires=("virgl_test_server",),
        server="virgl_test_server",
        server_args=("--use-egl-surfaceless", "--use-gles"),
        server_env={
            "MESA_NO_ERROR": "1",
            "MESA_GL_VERSION_OVERRIDE": "4.3COMPAT",
            "MESA_GLES_VERSION_OVERRIDE": "3.2",
            "GALLIUM_DRIVER": "zink",
            "ZINK_DESCRIPTORS": "lazy",
        },
    ),
    Preset(
        # Simplified to the doc's own direct-zink client command
        # (GALLIUM_DRIVER=zink MESA_GL_VERSION_OVERRIDE=4.0, no server at
        # all — it scored highest of every native option, 121-124). The
        # previous env here (MESA_GL_VERSION_OVERRIDE=4.3COMPAT,
        # MESA_GLES_VERSION_OVERRIDE=3.2, ZINK_DESCRIPTORS=lazy) was
        # actually the *server*-side flavor of zink from the "virgl" combo
        # above, mistakenly applied as this preset's *client* env instead.
        name="zink",
        env={"GALLIUM_DRIVER": "zink", "MESA_GL_VERSION_OVERRIDE": "4.0"},
        adreno_only=True,
    ),
    Preset(
        name="turnip",
        # TU_DEBUG=noconform dropped: LinuxDroidMaster/Termux-Desktops'
        # own docs list it only for the *proot* Turnip invocation; the
        # separate native-Termux Turnip section uses just
        # MESA_LOADER_DRIVER_OVERRIDE=zink with no TU_DEBUG at all. Needs
        # the mesa-vulkan-icd-freedreno-dri3 package (a Vulkan ICD, not a
        # standalone binary shutil.which can detect — no `requires` check
        # here; a missing ICD will surface as a real glmark2 failure in
        # the log instead).
        env={"MESA_LOADER_DRIVER_OVERRIDE": "zink"},
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
# because the binary name and the pkg name aren't always the same.
# virgl_test_server_android ships in virglrenderer-android;
# virgl_test_server (a *different* binary — the zink-capable build) ships
# in virglrenderer-mesa-zink, confirmed via termux-user-repository/tur.
_BINARY_PACKAGES: dict[str, str] = {
    "glmark2": "glmark2",
    "virgl_test_server_android": "virglrenderer-android",
    "virgl_test_server": "virglrenderer-mesa-zink",
}


def _ensure_binary(binary: str, log: Log | None, _attempted: set[str] | None = None) -> bool:
    return native_packages.ensure_binary(
        binary, _BINARY_PACKAGES.get(binary, binary), log, _attempted
    )


def _stop_renderer() -> None:
    try:
        subprocess.run(["pkill", "-f", "virgl_test_server"], capture_output=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _start_renderer(preset: Preset, log: Log | None, _attempted: set[str] | None = None) -> bool:
    """Launches `preset.server` (e.g. virgl_test_server_android) as a
    background process before the GL client runs, if the preset needs
    one. Confirmed necessary from a real device run: glmark2 failed with
    "lost connection to rendering server on 8 read -1 22" because
    nothing had ever started virgl_test_server_android — checking the
    binary exists (candidates()/_ensure_binary) is not the same as it
    actually being *running*.
    """
    _stop_renderer()
    if preset.server is None:
        return True
    if not _ensure_binary(preset.server, log, _attempted):
        return False
    env = dict(os.environ)
    env.update(preset.server_env)
    try:
        subprocess.Popen(
            [preset.server, *preset.server_args],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        if log:
            log(f"{preset.name}: could not start {preset.server}: {exc}")
        return False
    time.sleep(1.5)
    try:
        check = subprocess.run(
            ["pgrep", "-f", preset.server], capture_output=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        check = None
    if check is None or check.returncode != 0:
        if log:
            log(f"{preset.name}: {preset.server} did not stay running")
        return False
    return True


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
                "termux-x11 is not running — glmark2 needs an active X "
                "display to open its (onscreen) benchmark window. Start "
                "Desktop first, then bench again."
            )
        return None

    if not _start_renderer(preset, log, _attempted):
        return None

    try:
        env = dict(os.environ)
        env["DISPLAY"] = x11.DISPLAY
        env.update(preset.env)
        # No --off-screen: a real device run (2026-08-26) failed with
        # "Error: main: Could not initialize canvas" on every preset with
        # it. Termux community reports (termux/termux-packages#16763)
        # confirm the working invocation against termux-x11 is a plain
        # onscreen window — e.g. ``DISPLAY=:1 GALLIUM_DRIVER=virpipe
        # glmark2`` — not an off-screen EGL surface, which termux-x11's
        # Mesa/virgl stack apparently doesn't support the way a full
        # desktop Mesa install (XLabs' proot-distro container, where
        # --off-screen was ported from) does.
        args = ["glmark2"]
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
    finally:
        # A leftover virgl_test_server_android would otherwise keep
        # running in the background after Bench finishes, and could
        # confuse the *next* preset's own renderer (or a later manual
        # Bench run) — always tear it down, success or failure.
        _stop_renderer()


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
