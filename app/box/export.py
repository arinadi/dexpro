"""dexpro box export — distrobox-style app/binary export.

Adapts distrobox-export's confirmed mechanism (wrapper script for
binaries; .desktop copy + Exec-rewrite for GUI apps), substituting
`proot-distro login` for `distrobox enter`. Genuinely new work — neither
XLabs nor dextop has any app-export/desktop-integration mechanism
(confirmed by grep in the initial research pass).

Fidelity tradeoff (build-task-phase3.md Task 2 — surface this in
--help/tooltips, don't oversell it): an exported app still crosses the
proot boundary for its own syscalls. Export only avoids nesting a
second full GUI session inside the container — it does not make the
app itself native-speed.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from . import manager

Log = Callable[[str], None]

DEFAULT_BIN_EXPORT_DIR = os.path.expanduser("~/.local/bin")
DESKTOP_APPLICATIONS_DIR = os.path.expanduser("~/.local/share/applications")
ICONS_DIR = os.path.expanduser("~/.local/share/icons")

FIDELITY_NOTE = (
    "exported apps still cross the proot boundary for their own syscalls — "
    "export avoids nesting a second GUI session, it does not make the app "
    "itself native-speed"
)

_SHEBANG = "#!/data/data/com.termux/files/usr/bin/bash"
_BIN_MARKER = "# dexpro-export"
_DESKTOP_MARKER_KEY = "X-Dexpro-Container"

_DESKTOP_SEARCH_DIRS = ("/usr/share/applications", "/root/.local/share/applications")

_EXEC_LINE = re.compile(r"^Exec=(.*)$", re.MULTILINE)
_ICON_LINE = re.compile(r"^Icon=(.*)$", re.MULTILINE)

# Best-effort icon resolution for a few conventional locations — not a
# full icon-theme lookup (out of scope for v1; icons are cosmetic, a
# missing one shouldn't block the export).
_ICON_CANDIDATE_TEMPLATES = (
    "/usr/share/icons/hicolor/48x48/apps/{name}.png",
    "/usr/share/icons/hicolor/scalable/apps/{name}.svg",
    "/usr/share/pixmaps/{name}.png",
)


# --- Binary export ---


def wrapper_script(container: str, binary_path: str) -> str:
    return (
        f"{_SHEBANG}\n"
        f"{_BIN_MARKER} container={container} bin={binary_path}\n"
        f'exec proot-distro login {container} --shared-tmp -- {binary_path} "$@"\n'
    )


def is_dexpro_bin_export(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(200)
    except OSError:
        return False
    return _BIN_MARKER in head


def export_bin(
    container: str, binary_path: str, export_dir: str | None = None, log: Log | None = None
) -> str | None:
    export_dir = export_dir or DEFAULT_BIN_EXPORT_DIR
    name = os.path.basename(binary_path)
    target = os.path.join(export_dir, name)
    try:
        os.makedirs(export_dir, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(wrapper_script(container, binary_path))
        os.chmod(target, 0o755)
    except OSError as exc:
        if log:
            log(f"error: could not write wrapper at {target}: {exc}")
        return None
    if log:
        log(f"exported {binary_path} from '{container}' to {target} ({FIDELITY_NOTE})")
    return target


def delete_bin_export(name: str, export_dir: str | None = None, log: Log | None = None) -> bool:
    export_dir = export_dir or DEFAULT_BIN_EXPORT_DIR
    target = os.path.join(export_dir, name)
    if not os.path.exists(target):
        return True
    if not is_dexpro_bin_export(target):
        if log:
            log(f"error: {target} wasn't created by dexpro export — refusing to delete it")
        return False
    try:
        os.remove(target)
        return True
    except OSError as exc:
        if log:
            log(f"error: could not remove {target}: {exc}")
        return False


# --- App (.desktop) export ---


def desktop_find_script() -> str:
    """The shell script `list_desktop_files` runs inside the container.

    Confirmed on-device: joining the per-dir `find` invocations with a
    bare space produced one malformed command (the second `find ...`
    was parsed as more arguments to the first, not a separate command)
    rather than two sequential ones — real bug, caught because
    discovery silently returned nothing against a container with a real
    .desktop file seeded in it. Joined with `;` now — exposed as its own
    function so the separator can be tested without a real proot-distro
    binary.
    """
    return "; ".join(
        f"find {d} -maxdepth 1 -name '*.desktop' 2>/dev/null" for d in _DESKTOP_SEARCH_DIRS
    )


def list_desktop_files(container: str, log: Log | None = None) -> list[str]:
    """Finds .desktop files inside the container across the standard
    search dirs."""
    script = desktop_find_script()
    full = manager.login_command(container, ["sh", "-c", script])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, text=True)
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: could not list .desktop files: {exc}")
        return []


def patch_desktop_exec(content: str, container: str) -> str:
    """Rewrites the Exec= line to prefix a proot-distro login invocation
    and tags the file with the owning container — mirrors distrobox-
    export's Exec-rewrite approach, substituting proot-distro login for
    distrobox enter."""
    match = _EXEC_LINE.search(content)
    if match:
        original_exec = match.group(1)
        new_exec = f"proot-distro login {container} --shared-tmp -- {original_exec}"
        content = _EXEC_LINE.sub(f"Exec={new_exec}", content, count=1)
    return content.rstrip("\n") + f"\n{_DESKTOP_MARKER_KEY}={container}\n"


def is_dexpro_app_export(path: str, container: str | None = None) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False
    match = re.search(rf"^{_DESKTOP_MARKER_KEY}=(.*)$", content, re.MULTILINE)
    if not match:
        return False
    return container is None or match.group(1).strip() == container


def export_app(container: str, desktop_path: str, log: Log | None = None) -> str | None:
    """Copies the container's .desktop file to the host, rewrites its
    Exec= line, and copies its referenced icon if present."""
    full = manager.login_command(container, ["cat", desktop_path])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, text=True, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: could not read {desktop_path} from '{container}': {exc}")
        return None

    patched = patch_desktop_exec(result.stdout, container)

    filename = os.path.basename(desktop_path)
    target = os.path.join(DESKTOP_APPLICATIONS_DIR, filename)
    try:
        os.makedirs(DESKTOP_APPLICATIONS_DIR, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(patched)
    except OSError as exc:
        if log:
            log(f"error: could not write {target}: {exc}")
        return None

    _export_icon(container, result.stdout, log=log)

    if log:
        log(f"exported {desktop_path} from '{container}' to {target} ({FIDELITY_NOTE})")
    return target


def _export_icon(container: str, desktop_content: str, log: Log | None = None) -> None:
    match = _ICON_LINE.search(desktop_content)
    if not match:
        return
    icon_name = match.group(1).strip()
    if not icon_name or os.path.isabs(icon_name):
        # An absolute path points inside the container's own filesystem
        # — not resolvable here without assuming a rootfs layout. Named
        # icons (the common .desktop convention) are handled below.
        return
    for template in _ICON_CANDIDATE_TEMPLATES:
        candidate = template.format(name=icon_name)
        full = manager.login_command(container, ["test", "-f", candidate])
        try:
            probe = subprocess.run(full, capture_output=True, timeout=10)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
        if probe.returncode == 0:
            _copy_icon(container, candidate, icon_name, log=log)
            return


def _copy_icon(container: str, container_path: str, icon_name: str, log: Log | None) -> None:
    ext = os.path.splitext(container_path)[1]
    target = os.path.join(ICONS_DIR, f"{icon_name}{ext}")
    full = manager.login_command(container, ["cat", container_path])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"warning: could not copy icon {container_path}: {exc}")
        return
    try:
        os.makedirs(ICONS_DIR, exist_ok=True)
        with open(target, "wb") as f:
            f.write(result.stdout)
    except OSError as exc:
        if log:
            log(f"warning: could not write icon {target}: {exc}")


def delete_app_export(filename: str, log: Log | None = None) -> bool:
    target = os.path.join(DESKTOP_APPLICATIONS_DIR, filename)
    if not os.path.exists(target):
        return True
    if not is_dexpro_app_export(target):
        if log:
            log(f"error: {target} wasn't created by dexpro export — refusing to delete it")
        return False
    try:
        os.remove(target)
        return True
    except OSError as exc:
        if log:
            log(f"error: could not remove {target}: {exc}")
        return False


# --- Discovery ---


def list_exports() -> dict[str, list[str]]:
    apps: list[str] = []
    if os.path.isdir(DESKTOP_APPLICATIONS_DIR):
        for f in os.listdir(DESKTOP_APPLICATIONS_DIR):
            path = os.path.join(DESKTOP_APPLICATIONS_DIR, f)
            if f.endswith(".desktop") and is_dexpro_app_export(path):
                apps.append(f)
    binaries: list[str] = []
    if os.path.isdir(DEFAULT_BIN_EXPORT_DIR):
        for f in os.listdir(DEFAULT_BIN_EXPORT_DIR):
            path = os.path.join(DEFAULT_BIN_EXPORT_DIR, f)
            if is_dexpro_bin_export(path):
                binaries.append(f)
    return {"apps": apps, "binaries": binaries}
