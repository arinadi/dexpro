"""Doctor's core model and checks — build-task-phase4.md Tasks 1/2.

`Issue` ported from XLabs' NamedTuple directly — a clean, minimal model
with nothing proot-specific about its shape.

Honesty note on the Termux:X11 signing-variant check (flagged in
build-task-phase4.md as "a real, previously-undocumented pitfall worth
catching"): full verification would need APK-signature introspection
this session found no reliable, confirmed command for from inside
Termux's own shell. Rather than pretend to check it, this only confirms
the package is installed and marks the deeper signing-variant question
`unknown=True` — an honest gap, not a false pass.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import NamedTuple

from .. import const
from ..box import manager as box_manager
from ..box import packages as box_packages
from ..box import user as box_user
from ..native import audio, gpu, x11
from . import duplicates, electron, fonts

Log = Callable[[str], None]


class Issue(NamedTuple):
    name: str
    ok: bool
    detail: str = ""
    # Takes a logger — previously zero-argument, which meant a fix had no
    # way to report what it was actually doing back to the screen even
    # when the underlying function already tried to (gpu.bench() logs
    # "benchmarking X..." per preset, but the old `fix=lambda:
    # bool(gpu.bench())` dropped it on the floor). Reported live as
    # "tidak ada kelihatan command yang dijalankan" — no visible command,
    # no running log.
    fix: Callable[[Log], bool] | None = None
    unknown: bool = False


# --- Native-layer checks ---


def check_x11_socket() -> Issue:
    alive = x11.wait_for_socket(timeout=1.0, interval=0.2)
    detail = "" if alive else "no X11 server responding on the expected socket"
    return Issue("X11 socket", alive, detail)


def check_gpu_profile() -> Issue:
    preset = gpu.load_profile()
    vendor = gpu.detect_vendor()
    if preset.adreno_only and vendor != "adreno":
        detail = (
            f"persisted profile '{preset.name}' is Adreno-only but "
            f"detected vendor is '{vendor}'"
        )
        return Issue("GPU renderer", False, detail, fix=lambda log: bool(gpu.bench(log)))
    return Issue("GPU renderer", True, f"using '{preset.name}'")


def check_audio() -> Issue:
    running = audio.is_running()
    detail = "" if running else "PulseAudio isn't running"
    return Issue("Audio", running, detail, fix=lambda log: audio.ensure_server(log))


def check_wakelock_binary() -> Issue:
    present = shutil.which("termux-wake-lock") is not None
    detail = "" if present else "termux-wake-lock not found — session may be doze-throttled"
    return Issue("Wake-lock", present, detail)


def check_termux_x11_installed() -> Issue:
    present = shutil.which("termux-x11") is not None
    if not present:
        return Issue("Termux:X11", False, "termux-x11 package not installed")
    detail = "installed; signing-variant match (universal/sharedUid, GitHub/F-Droid) not verified"
    return Issue("Termux:X11", True, detail, unknown=True)


# --- Self-install checks ---
#
# Every one of these mirrors a real bug this session found by the user
# hitting a raw traceback: a bad Termux package name, a launcher symlink
# that resolved to the wrong directory, and a missing `pip install
# textual` step entirely. Doctor should have caught all three as a red
# row instead — that's the point of this section.

# Keep in sync with install.py's PACKAGE_GROUPS.
REQUIRED_TERMUX_PACKAGES: tuple[str, ...] = (
    "termux-x11-nightly",
    "virglrenderer-android",
    "pulseaudio",
    "dbus",
    "xfce4",
    "xfce4-terminal",
)


def check_textual_importable() -> Issue:
    present = importlib.util.find_spec("textual") is not None
    detail = "" if present else "not installed — run: pip install textual"
    return Issue("Textual", present, detail, fix=None if present else _fix_textual)


def _fix_textual(log: Log) -> bool:
    target = "textual>=8.2"  # keep in sync with pyproject.toml
    attempts = [
        [sys.executable, "-m", "pip", "install", target, "--quiet"],
        [sys.executable, "-m", "pip", "install", target, "--quiet", "--break-system-packages"],
        [sys.executable, "-m", "pip", "install", target, "--quiet", "--user"],
    ]
    for cmd in attempts:
        log(f"$ {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120, text=True)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            log(f"  {exc}")
            continue
        if result.returncode == 0:
            return True
        log(f"  exit {result.returncode}: {(result.stderr or '').strip()}")
    return False


def check_launcher_resolves() -> Issue:
    link = os.path.join(const.PREFIX_BIN, "dexpro")
    if not os.path.exists(link):
        return Issue("Launcher", False, f"{link} not found", fix=_fix_launcher)
    target = os.path.realpath(link)
    if not os.path.isfile(os.path.join(os.path.dirname(target), "app", "app.py")):
        detail = f"{link} resolves to {target}, which has no app/app.py next to it"
        return Issue("Launcher", False, detail, fix=_fix_launcher)
    return Issue("Launcher", True, f"resolves to {target}")


def _fix_launcher(log: Log) -> bool:
    link = os.path.join(const.PREFIX_BIN, "dexpro")
    log(f"linking {link} -> {const.LAUNCHER_SRC}")
    try:
        if os.path.islink(link) or os.path.exists(link):
            os.remove(link)
        os.symlink(const.LAUNCHER_SRC, link)
        os.chmod(const.LAUNCHER_SRC, 0o755)
        return True
    except OSError as exc:
        log(f"  {exc}")
        return False


def check_termux_packages() -> Issue:
    missing = [p for p in REQUIRED_TERMUX_PACKAGES if not duplicates.termux_has(p)]
    if not missing:
        return Issue("Termux packages", True, "all present")
    return Issue(
        "Termux packages", False, f"missing: {', '.join(missing)}",
        fix=lambda log: _fix_missing_packages(missing, log),
    )


def _fix_missing_packages(missing: list[str], log: Log) -> bool:
    cmd = ["pkg", "install", "-y", *missing]
    log(f"$ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300, text=True)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log(f"  {exc}")
        return False
    if result.returncode != 0:
        log(f"  exit {result.returncode}: {(result.stderr or '').strip()}")
    return result.returncode == 0


def check_fonts() -> Issue:
    missing = [p for p in fonts.PACKAGES if not duplicates.termux_has(p)]
    if not missing:
        return Issue("Fonts", True, "installed")
    return Issue(
        "Fonts", False, f"missing: {', '.join(missing)}",
        fix=lambda log: fonts.install(log) and fonts.patch_terminal_font(log=log),
    )


NATIVE_CHECKS: tuple[Callable[[], Issue], ...] = (
    check_x11_socket,
    check_gpu_profile,
    check_audio,
    check_wakelock_binary,
    check_termux_x11_installed,
    check_textual_importable,
    check_launcher_resolves,
    check_termux_packages,
    check_fonts,
)


def run_native_checks() -> list[Issue]:
    return [check() for check in NATIVE_CHECKS]


# --- Per-container checks ---


container_rootfs_path = box_manager.container_rootfs_path


def check_apt_lists(container: str) -> Issue:
    present = box_packages.lists_present(container)
    detail = "" if present else "apt lists not populated — run apt update"
    return Issue(f"[{container}] apt lists", present, detail)


def check_user_uid_mapped(container: str, username: str) -> Issue:
    rootfs = container_rootfs_path(container)
    if rootfs is None:
        detail = "could not resolve rootfs path"
        return Issue(f"[{container}] user '{username}'", False, detail, unknown=True)
    home = os.path.join(rootfs, "home", username)
    matched = box_user.owner_matches_host(home)
    detail = "" if matched else f"{home} isn't owned by the real host UID"
    return Issue(f"[{container}] user '{username}'", matched, detail)


def check_duplicates(container: str) -> Issue:
    dupes = duplicates.find_duplicates(container)
    if not dupes:
        return Issue(f"[{container}] duplicate tools", True, "none found")
    return Issue(
        f"[{container}] duplicate tools", False, f"also in Termux: {', '.join(dupes)}",
        fix=lambda log: duplicates.remove_termux_duplicates(dupes, log=log),
    )


def check_electron(container: str) -> Issue:
    unpatched = electron.find_unpatched(container)
    if not unpatched:
        return Issue(f"[{container}] Electron apps", True, "none need patching")
    return Issue(
        f"[{container}] Electron apps", False, f"{len(unpatched)} need --no-sandbox",
        fix=lambda log: bool(electron.scan_and_patch(container, log=log)),
    )


def run_container_checks(container: str, username: str | None = None) -> list[Issue]:
    issues = [check_apt_lists(container)]
    if username:
        issues.append(check_user_uid_mapped(container, username))
    issues.append(check_duplicates(container))
    issues.append(check_electron(container))
    return issues


def run_all_checks(containers: list[str] | None = None) -> list[Issue]:
    if containers is None:
        containers = [c["name"] for c in box_manager.list_containers()]
    issues = run_native_checks()
    for container in containers:
        issues.extend(run_container_checks(container))
    return issues
