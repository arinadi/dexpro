#!/usr/bin/env python3
"""dexpro installer — stage 2 (run by install.sh after the repo checkout).

Installs the Python libraries app/app.py needs, the Termux packages the
native session needs (build-task-phase1.md Prerequisites), and links the
`dexpro` launcher onto PATH.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

MIN_FREE_GB = 4.0  # the x11-repo/xfce4 package set plus caches, comfortably

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
#
# "theme" and "multimedia" (2026-08-26, re-researched from dextop's actual
# termux-packages script — the Termux-side one, not XLabs' fonts.py which
# turned out to be for a Debian *container* via apt-get, a different
# package namespace entirely): dextop's own xfce_themes_list only has
# adwaita-icon-theme active for Termux (arc-theme is commented out there,
# specifically for the Termux side — not carried over here on the same
# caution this project has already needed twice with cross-context package
# names). Packages only, not applied as the active theme via xfconf: doing
# that means running xfconf-query against the same D-Bus session
# native/session.py hands off to xfce4-session, and this project has no
# device to verify that sequencing works cleanly — the packages just being
# available (for XFCE's own Settings Manager, or the user's own choice)
# is the safe, bounded piece of this.
PACKAGE_GROUPS = {
    "Termux:X11": ["termux-x11-nightly"],
    "graphics": ["virglrenderer-android"],
    "audio/dbus": ["pulseaudio", "dbus"],
    "desktop": ["xfce4", "xfce4-terminal"],
    "theme": ["papirus-icon-theme", "adwaita-icon-theme"],
    "multimedia": [
        "ffmpeg",
        "flac",
        "gstreamer",
        "gst-plugins-good",
        "gst-plugins-bad",
        "gst-plugins-ugly",
        "gst-plugins-base",
    ],
}


def preflight() -> None:
    """Environment checks before anything is installed — ported from
    XLabs' preflight.py (ran before this session found install.py never
    checked internet/storage/Python version at all, unlike XLabs). Pure
    stdlib on purpose: this runs before pip has installed anything.
    Only Internet is fatal — the rest describe conditions the rest of
    this script is about to hit anyway, so they're warnings, not a
    reason to refuse to try.
    """
    print(">>> Checking environment")

    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5).close()
        print("    ok Internet")
    except OSError:
        print("    !! No internet connection — cannot install")
        raise SystemExit(1) from None

    for path in ("/data", os.path.expanduser("~"), "/"):
        try:
            free_gb = shutil.disk_usage(path).free / (1024**3)
        except OSError:
            continue
        if free_gb < MIN_FREE_GB:
            print(f"    !! Storage: only {free_gb:.1f} GB free (recommend {MIN_FREE_GB:g}+ GB)")
        else:
            print(f"    ok Storage: {free_gb:.1f} GB free")
        break

    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        print(f"    !! Python {major}.{minor} — dexpro needs 3.10+")
    else:
        print(f"    ok Python {major}.{minor}")


def run(cmd: list[str], check: bool = True) -> int:
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if check:
        result.check_returncode()
    return result.returncode


def install_libs() -> None:
    """Installs pyproject.toml's runtime dependency (textual) into Termux's
    Python. Previously missing entirely: install.py never ran pip, so
    `dexpro install` succeeded but `dexpro` then failed with
    ModuleNotFoundError: No module named 'textual'. Mirrors XLabs'
    install_libs() fallback chain — Termux's Python is externally managed
    (PEP 668) on newer releases, so the plain install is tried first and
    the override flags only as a fallback.
    """
    target = "textual>=8.2"  # keep in sync with pyproject.toml's [project.dependencies]
    attempts = [
        [sys.executable, "-m", "pip", "install", target, "--quiet"],
        [sys.executable, "-m", "pip", "install", target, "--quiet", "--break-system-packages"],
        [sys.executable, "-m", "pip", "install", target, "--quiet", "--user"],
    ]
    for cmd in attempts:
        if run(cmd, check=False) == 0:
            print(">>> textual installed")
            return
    raise RuntimeError("could not install textual")


def install_packages() -> None:
    run(["pkg", "update", "-y"])
    # x11-repo for the desktop packages below; tur-repo (Termux User
    # Repository) so the in-app Termux Store has a community package
    # source available out of the box, matching XLabs' own
    # install_termux_packages(), which enables both together.
    run(["pkg", "install", "-y", "x11-repo", "tur-repo"])
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
    preflight()
    install_libs()
    install_packages()
    link_launcher()
    print("")
    print("dexpro installed. Run: dexpro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
