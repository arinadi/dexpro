"""Firefox performance tuning for proot's ptrace overhead — ported from
XLabs' browser.py, "safe" tier only.

Every open/stat/read/write a browser makes inside a dexpro-box
container is intercepted in userspace by proot, so process count and
disk-write frequency dominate perceived lag far more than raw engine
speed. XLabs splits its tuning into two tiers; only the first is
ported here:

- "safe" tuning (this module): no downside beyond what it changes on
  purpose (fewer processes, less disk I/O, no telemetry) — safe for
  Doctor's own Fix to apply automatically.
- "reduced security" (Fission site isolation, Safe Browsing warnings
  traded for less overhead): XLabs itself never wires this into Fix,
  requiring its own explicit confirmation. Not ported here at all —
  out of scope for this pass, revisit if wanted later.

Chromium's --no-sandbox/--renderer-process-limit .desktop flag patching
(XLabs' apply_chromium_tuning, on top of its desktopfiles.py) is also
not ported: it needs a general .desktop Exec= rewrite helper dexpro
doesn't have (electron.py's own patcher is Electron-specific), and
Chromium tuning is lower value than Firefox's — narrower scope for a
first pass.

Proot-only, box-only: writes directly to the container's host-side
rootfs (mirror.py's own pattern via manager.container_rootfs_path),
same reason isolation.py/iobench.py are box-only — the native session
has no browser of its own to tune and no proot boundary these
optimizations exist to work around.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from ..native import gpu
from . import manager

Log = Callable[[str], None]

FIREFOX_BIN = "/usr/bin/firefox-esr"
FIREFOX_PREFS_DIR = "/usr/lib/firefox-esr/browser/defaults/preferences"
FIREFOX_VIDEO_PREFS_FILE = f"{FIREFOX_PREFS_DIR}/dexpro-video.js"
FIREFOX_SAFE_PREFS_FILE = f"{FIREFOX_PREFS_DIR}/dexpro-perf.js"

# Firefox scans FIREFOX_PREFS_DIR for default preferences, so a file
# there applies before any profile exists and without locking
# anything: every value below can still be changed in about:config.
FIREFOX_VIDEO_PREFS = """// dexpro — video defaults for proot on Android.
//
// YouTube serves VP9 or AV1 by default. Neither can be hardware
// decoded in this stack: there is no VA-API through proot, so both
// are decoded on the CPU, which is what makes playback stutter.
// Turning them off makes YouTube fall back to H.264, far cheaper to
// decode. VirGL doesn't help here — it accelerates OpenGL rendering
// and compositing, not video decode.
//
// Defaults, not locks — change these in about:config if you want AV1
// back on a device that can afford it.
pref("media.mediasource.vp9.enabled", false);
pref("media.av1.enabled", false);
"""

FIREFOX_SAFE_PREFS_TEMPLATE = """// dexpro — performance defaults for proot on Android.
//
// Every open/stat/read/write a browser makes goes through proot's
// ptrace intercept, so process count and write frequency matter far
// more here than raw engine speed. None of these cost a feature
// beyond what they say.
//
// Defaults, not locks — change any of these in about:config.
user_pref("dom.ipc.processCount", 2);
user_pref("dom.ipc.processCount.webIsolated", 1);
user_pref("browser.preferences.defaultPerformanceSettings.enabled", false);
user_pref("browser.sessionstore.interval", 600000);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.cache.disk.enable", false);
user_pref("browser.cache.memory.enable", true);
user_pref("browser.cache.memory.capacity", 131072);
user_pref("toolkit.telemetry.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("dom.w3c_touch_events.enabled", 1);
user_pref("ui.prefersReducedMotion", 1);
user_pref("general.smoothScroll", false);
user_pref("browser.tabs.unloadOnLowMemory", true);
{webrender_line}
"""


def _gpu_accelerated() -> bool:
    """Whether a real GPU preset (not software, not unmeasured) is
    active. A dexpro-box container's GUI apps render through the same
    native X11/GPU pipeline as everything else (there's no separate
    proot-side X server — see PRD.md's native-layer architecture), so
    the native GPU profile is the right signal here too. gfx.webrender
    only helps if virgl/zink actually works, and is worse than nothing
    if the desktop fell back to software rendering."""
    return gpu.load_profile().name != "software"


def _container_path(container: str, path: str) -> str | None:
    rootfs = manager.container_rootfs_path(container)
    if rootfs is None:
        return None
    return os.path.join(rootfs, path.lstrip("/"))


def _write_prefs_file(container: str, target_path: str, body: str, log: Log) -> bool:
    if manager.container_rootfs_path(container) is None:
        log(f"error: no such container '{container}'")
        return False
    directory = _container_path(container, FIREFOX_PREFS_DIR)
    if directory is None or not os.path.isdir(directory):
        log(f"  {FIREFOX_PREFS_DIR} does not exist in '{container}' — is Firefox installed?")
        return False
    target = _container_path(container, target_path)
    try:
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except OSError as exc:
        log(f"  could not write {target_path}: {exc}")
        return False
    log(f"  wrote {target_path}")
    return True


def firefox_present(container: str) -> bool:
    path = _container_path(container, FIREFOX_BIN)
    return path is not None and os.path.exists(path)


def firefox_video_prefs_ok(container: str) -> bool:
    path = _container_path(container, FIREFOX_VIDEO_PREFS_FILE)
    return path is not None and os.path.exists(path)


def firefox_safe_tuning_ok(container: str) -> bool:
    path = _container_path(container, FIREFOX_SAFE_PREFS_FILE)
    return path is not None and os.path.exists(path)


def apply_firefox_tuning(container: str, log: Log) -> bool:
    """Writes both the video and safe-performance prefs files in one
    pass — Doctor's Fix action for this check does both together, same
    granularity XLabs' own Fix uses."""
    video_ok = _write_prefs_file(container, FIREFOX_VIDEO_PREFS_FILE, FIREFOX_VIDEO_PREFS, log)

    webrender_line = (
        'user_pref("gfx.webrender.all", true);'
        if _gpu_accelerated()
        else 'user_pref("gfx.webrender.software", true);'
    )
    body = FIREFOX_SAFE_PREFS_TEMPLATE.format(webrender_line=webrender_line)
    safe_ok = _write_prefs_file(container, FIREFOX_SAFE_PREFS_FILE, body, log)

    if video_ok and safe_ok:
        log("  restart Firefox for it to take effect")
    return video_ok and safe_ok
