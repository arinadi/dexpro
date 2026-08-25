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

# termux-x11-nightly/virglrenderer/xfce4/xfce4-terminal all live in
# x11-repo, not termux-main — it must be installed AND its package list
# picked up (a second `pkg update`) before apt can see them at all.
PACKAGES = (
    "termux-x11-nightly",
    "virglrenderer",
    "pulseaudio-utils",
    "dbus",
    "xfce4",
    "xfce4-terminal",
)


def run(cmd: list[str]) -> None:
    print(f">>> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def install_packages() -> None:
    run(["pkg", "update", "-y"])
    run(["pkg", "install", "-y", "x11-repo"])
    run(["pkg", "update", "-y"])
    run(["pkg", "install", "-y", *PACKAGES])


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
