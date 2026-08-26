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

No Fonts check: removed 2026-08-25 after a real device confirmed
fonts-noto-color-emoji isn't a real Termux package — doctor/fonts.py
ported XLabs' Debian package names verbatim without re-checking they
exist under Termux's own `pkg`, so the check could never pass. The
fonts.py module itself is untouched (patch_terminal_font() is still
useful independent of package availability); only the broken Doctor
check was removed. Revisit once real Termux font package names are
confirmed.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable
from typing import NamedTuple

from .. import const
from ..box import browser
from ..box import manager as box_manager
from ..box import packages as box_packages
from ..box import user as box_user
from ..native import audio, gpu, x11
from ..native import packages as native_packages
from . import duplicates, electron

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
        return Issue("GPU renderer", False, detail, fix=_fix_gpu_profile)
    return Issue("GPU renderer", True, f"using '{preset.name}'")


def _fix_gpu_profile(log: Log) -> bool:
    # bool(gpu.bench(log)) alone never called save_profile() — the
    # benchmark ran for real but its result was discarded, so this
    # "fix" never actually changed the persisted profile it was meant
    # to correct. Found while wiring the same gpu.bench() call into a
    # manual Settings "Bench" button.
    result = gpu.bench(log)
    if result is None:
        return False
    preset, score = result
    gpu.save_profile(preset, score)
    return True


def check_audio() -> Issue:
    if not audio.is_enabled():
        # Off is the deliberate default (dextop's own — battery/CPU
        # cost), not a fault. Reporting it as a red "not ok" would make
        # Doctor flag the expected, chosen state as broken every single
        # time on a fresh install.
        return Issue("Audio", True, "disabled in Settings (default)")
    running = audio.is_running()
    detail = (
        ""
        if running
        else (
            "enabled in Settings but PulseAudio isn't running — if it worked "
            "right after Start Desktop but died on its own, Android's "
            "phantom process killer (12+) is a common cause (adb: "
            "settings_enable_monitor_phantom_procs, or Developer Options). "
            "Fix will restart it either way."
        )
    )
    return Issue("Audio", running, detail, fix=lambda log: audio.ensure_server(log))


def check_wakelock_binary() -> Issue:
    present = shutil.which("termux-wake-lock") is not None
    detail = "" if present else "termux-wake-lock not found — session may be doze-throttled"
    if present:
        return Issue("Wake-lock", present, detail)
    # termux-wake-lock ships in core termux-tools (wakelock.py's own
    # docstring confirms this from termux-wake-lock.in's source) — always
    # present in a working Termux install, so this fix is a rare-edge-case
    # repair path, not something expected to actually fire often.
    return Issue(
        "Wake-lock",
        present,
        detail,
        fix=lambda log: native_packages.ensure_binary("termux-wake-lock", "termux-tools", log),
    )


def check_termux_x11_installed() -> Issue:
    present = shutil.which("termux-x11") is not None
    if not present:
        return Issue(
            "Termux:X11",
            False,
            "termux-x11 package not installed",
            fix=lambda log: native_packages.ensure_binary("termux-x11", "termux-x11-nightly", log),
        )
    detail = "installed; signing-variant match (universal/sharedUid, GitHub/F-Droid) not verified"
    return Issue("Termux:X11", True, detail, unknown=True)


# Termux:X11 the Termux *package* (checked above) is not the same thing
# as the com.termux.x11 Android *app* — the desktop starts but has
# nowhere to render without the app installed, per XLabs' own
# check_x11_app() docstring. Ported from XLabs' preflight.py: querying
# it from inside Termux is fiddly enough that XLabs' own comments call
# it out explicitly — pm needs --user 0 on devices with a work profile
# or Samsung Secure Folder (a bare query fails with "Shell does not
# have permission to access user <n>"), and stdin has to be off the
# terminal or it trips over the character device.
X11_APP_PACKAGE = "com.termux.x11"
X11_APK_URL = "https://github.com/termux/termux-x11/releases/tag/nightly"


def check_termux_x11_app() -> Issue:
    pm = shutil.which("pm")
    if pm is None and os.path.exists("/system/bin/pm"):
        pm = "/system/bin/pm"
    if pm is None:
        return Issue("Termux:X11 app", False, "cannot query installed apps (no pm)", unknown=True)

    attempts = (
        [pm, "list", "packages", "--user", "0", X11_APP_PACKAGE],
        [pm, "list", "packages", X11_APP_PACKAGE],
    )
    for argv in attempts:
        try:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        out = result.stdout or ""
        if f"package:{X11_APP_PACKAGE}" in out:
            return Issue("Termux:X11 app", True, "installed")

        # An empty, successful query is a real answer: the app isn't
        # there — distinct from pm refusing to answer at all.
        lowered = out.lower()
        refused = (
            result.returncode != 0
            or "exception" in lowered
            or "denial" in lowered
            or "does not have permission" in lowered
        )
        if not refused:
            return Issue("Termux:X11 app", False, f"not installed — sideload from {X11_APK_URL}")

    return Issue("Termux:X11 app", False, "pm refused the query — check manually", unknown=True)


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
    "virglrenderer-mesa-zink",
    "mesa-zink",
    "vulkan-loader-android",
    "mesa-vulkan-icd-freedreno-dri3",
    "pulseaudio",
    "dbus",
    "xfce4",
    "xfce4-terminal",
)

MIN_FREE_GB = 4.0  # ported from install.py's preflight() — same threshold


def check_internet() -> Issue:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5).close()
        return Issue("Internet", True, "connected")
    except OSError:
        return Issue("Internet", False, "no connection")


def check_storage() -> Issue:
    for path in ("/data", os.path.expanduser("~"), "/"):
        try:
            free_gb = shutil.disk_usage(path).free / (1024**3)
        except OSError:
            continue
        ok = free_gb >= MIN_FREE_GB
        detail = f"{free_gb:.1f} GB free"
        if not ok:
            detail += f" (recommend {MIN_FREE_GB:g}+ GB)"
        return Issue("Storage", ok, detail)
    return Issue("Storage", False, "could not determine free space", unknown=True)


def check_python_version() -> Issue:
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 10)
    version = f"{major}.{minor}"
    return Issue("Python", ok, version if ok else f"{version} (need 3.10+)")


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


NATIVE_CHECKS: tuple[Callable[[], Issue], ...] = (
    check_x11_socket,
    check_gpu_profile,
    check_audio,
    check_wakelock_binary,
    check_termux_x11_installed,
    check_termux_x11_app,
    check_textual_importable,
    check_launcher_resolves,
    check_termux_packages,
    check_internet,
    check_storage,
    check_python_version,
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


def check_firefox_tuning(container: str) -> Issue:
    if not browser.firefox_present(container):
        return Issue(f"[{container}] Firefox tuning", True, "Firefox not installed")
    tuned = browser.firefox_video_prefs_ok(container) and browser.firefox_safe_tuning_ok(container)
    if tuned:
        return Issue(f"[{container}] Firefox tuning", True, "applied")
    return Issue(
        f"[{container}] Firefox tuning", False, "not applied — proot overhead untuned",
        fix=lambda log: browser.apply_firefox_tuning(container, log),
    )


def run_container_checks(container: str, username: str | None = None) -> list[Issue]:
    issues = [check_apt_lists(container)]
    if username:
        issues.append(check_user_uid_mapped(container, username))
    issues.append(check_duplicates(container))
    issues.append(check_electron(container))
    issues.append(check_firefox_tuning(container))
    return issues


def run_all_checks(containers: list[str] | None = None) -> list[Issue]:
    if containers is None:
        containers = [c["name"] for c in box_manager.list_containers()]
    issues = run_native_checks()
    for container in containers:
        issues.extend(run_container_checks(container))
    return issues
