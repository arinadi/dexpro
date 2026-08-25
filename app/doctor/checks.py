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

import os
import shutil
from collections.abc import Callable
from typing import NamedTuple

from ..box import manager as box_manager
from ..box import packages as box_packages
from ..box import user as box_user
from ..native import audio, gpu, x11


class Issue(NamedTuple):
    name: str
    ok: bool
    detail: str = ""
    fix: Callable[[], bool] | None = None
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
        return Issue("GPU renderer", False, detail, fix=lambda: bool(gpu.bench()))
    return Issue("GPU renderer", True, f"using '{preset.name}'")


def check_audio() -> Issue:
    running = audio.is_running()
    detail = "" if running else "PulseAudio isn't running"
    return Issue("Audio", running, detail, fix=lambda: audio.ensure_server())


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


NATIVE_CHECKS: tuple[Callable[[], Issue], ...] = (
    check_x11_socket,
    check_gpu_profile,
    check_audio,
    check_wakelock_binary,
    check_termux_x11_installed,
)


def run_native_checks() -> list[Issue]:
    return [check() for check in NATIVE_CHECKS]


# --- Per-container checks ---


def container_rootfs_path(container: str) -> str | None:
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    candidate = os.path.join(
        prefix, "var", "lib", "proot-distro", "containers", container, "rootfs"
    )
    return candidate if os.path.isdir(candidate) else None


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


def run_container_checks(container: str, username: str | None = None) -> list[Issue]:
    issues = [check_apt_lists(container)]
    if username:
        issues.append(check_user_uid_mapped(container, username))
    return issues


def run_all_checks(containers: list[str] | None = None) -> list[Issue]:
    if containers is None:
        containers = [c["name"] for c in box_manager.list_containers()]
    issues = run_native_checks()
    for container in containers:
        issues.extend(run_container_checks(container))
    return issues
