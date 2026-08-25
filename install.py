#!/usr/bin/env python3
"""dexpro installer — stage 2 (run by install.sh after the repo checkout).

Installs the Termux packages the native session needs (build-task-
phase1.md Prerequisites) and links the `dexpro` launcher onto PATH.
"""

from __future__ import annotations

import os
import subprocess
import sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# termux-x11-nightly/virglrenderer-android/xfce4/xfce4-terminal all live in
# x11-repo, not termux-main — it must be installed AND its package list
# picked up (a second `pkg update`) before apt can see them at all.
#
# Installed in labeled groups, each retried package-by-package on group
# failure: apt fails an ENTIRE `pkg install` line if even one name in it is
# unavailable, which would otherwise take down unrelated packages (xfce4,
# dbus, ...) alongside the bad one. Mirrors XLabs' install_termux_packages().
# virglrenderer-android (not bare "virglrenderer") is the package that
# actually provides virgl_test_server_android, which app/native/gpu.py's
# "virgl" preset requires. "pulseaudio" (not Debian-style "pulseaudio-utils"
# — Termux doesn't split them) provides both the daemon and pactl, which
# app/native/audio.py needs.
PACKAGE_GROUPS = {
    "Termux:X11": ["termux-x11-nightly"],
    "graphics": ["virglrenderer-android"],
    "audio/dbus": ["pulseaudio", "dbus"],
    "desktop": ["xfce4", "xfce4-terminal"],
}


def run(cmd: list[str], check: bool = True) -> int:
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if check:
        result.check_returncode()
    return result.returncode


def install_packages() -> None:
    run(["pkg", "update", "-y"])
    run(["pkg", "install", "-y", "x11-repo"])
    run(["pkg", "update", "-y"])

    for label, packages in PACKAGE_GROUPS.items():
        if run(["pkg", "install", "-y", *packages], check=False) == 0:
            continue
        print(f">>> {label} failed as a group, retrying one at a time")
        missing = [p for p in packages if run(["pkg", "install", "-y", p], check=False) != 0]
        if missing:
            raise RuntimeError(f"{label}: could not install: {', '.join(missing)}")


def link_launcher() -> None:
    prefix_bin = os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "bin")
    target = os.path.join(prefix_bin, "dexpro")
    source = os.path.join(REPO_DIR, "dexpro")
    if os.path.islink(target) or os.path.exists(target):
        os.remove(target)
    os.symlink(source, target)
    os.chmod(source, 0o755)
    print(f">>> linked {source} -> {target}")


def main() -> int:
    install_packages()
    link_launcher()
    print("")
    print("dexpro installed. Run: dexpro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
