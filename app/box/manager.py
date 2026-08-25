"""Thin subprocess wrapper over the proot-distro v5.x CLI.

proot-distro was rewritten in Python as of v5.x (current at research
time: v5.8.0) — it's a Docker/OCI-based tool now, not the old fixed-
distro bash tool. This module wraps its CLI rather than reimplementing
image acquisition (build-task-phase2.md's "Critical correction"):
install/list/remove/rename/backup/restore/search all already exist
upstream. Do not port dextop's container-image manual tar.xz extraction.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from . import isolation

Log = Callable[[str], None]

BINARY = "proot-distro"
MIN_VERSION = (5, 0, 0)


def container_rootfs_path(name: str) -> str | None:
    """Host-side path to a container's rootfs, or None if it doesn't
    exist. Canonical home for this lookup — doctor/checks.py and
    box/mirror.py both need it and must not each derive it separately."""
    prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
    candidate = os.path.join(prefix, "var", "lib", "proot-distro", "containers", name, "rootfs")
    return candidate if os.path.isdir(candidate) else None


def _run(
    args: list[str], check: bool = True, timeout: float | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BINARY, *args], capture_output=True, text=True, check=check, timeout=timeout
    )


def version() -> str | None:
    """proot-distro (5.8.0, confirmed on-device this session) has no
    `--version` flag — it's an unrecognized top-level command, which
    triggers the generic help screen. That help screen happens to end
    with a "PRoot-Distro version 'X.Y.Z' by Termux (...)" footer, which
    is the only place the version actually appears — `help` reliably
    reaches it without depending on --version being treated as an error
    in some future release."""
    try:
        result = _run(["help"], check=False, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    combined = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"PRoot-Distro version '([\d.]+)'", combined)
    return match.group(1) if match else None


def parse_version(raw: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def check_version(log: Log | None = None) -> bool:
    """Pin a minimum tested version — do not assume backward
    compatibility with pre-5.x installs, the CLI surface changed
    substantially with the rewrite (build-task-phase2.md's Version guard)."""
    raw = version()
    if raw is None:
        if log:
            log("error: proot-distro not found")
        return False
    parsed = parse_version(raw)
    if parsed is None:
        if log:
            log(f"warning: could not parse proot-distro version from {raw!r}")
        return True  # don't block on an unparseable version string
    if parsed < MIN_VERSION:
        if log:
            got = ".".join(map(str, parsed))
            want = ".".join(map(str, MIN_VERSION))
            log(
                f"warning: proot-distro {got} is older than the tested "
                f"baseline {want} — the v5.x CLI surface this module "
                "assumes may not match"
            )
        return False
    return True


def install(image: str, name: str, log: Log | None = None) -> bool:
    if log:
        log(f"$ proot-distro install {image} --name {name}")
    try:
        _run(["install", image, "--name", name], timeout=600)
        if log:
            log("done")
        return True
    except subprocess.CalledProcessError as exc:
        if log:
            log(f"error: proot-distro install failed: {exc.stderr}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro install failed: {exc}")
        return False


def remove(name: str, log: Log | None = None) -> bool:
    if log:
        log(f"$ proot-distro remove {name}")
    try:
        _run(["remove", name], timeout=60)
        if log:
            log("done")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro remove failed: {exc}")
        return False


def rename(name: str, new_name: str, log: Log | None = None) -> bool:
    if log:
        log(f"$ proot-distro rename {name} {new_name}")
    try:
        _run(["rename", name, new_name], timeout=60)
        if log:
            log("done")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro rename failed: {exc}")
        return False


def list_containers() -> list[dict[str, str]]:
    """Returns [{"name": ...}, ...]. proot-distro's `list` output is
    plain text (not JSON) — parsed conservatively: one name per non-
    empty, non-header line's first token."""
    try:
        result = _run(["list"], timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return []
    containers = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(("name", "---", "container")):
            continue
        containers.append({"name": line.split()[0]})
    return containers


def search(query: str, log: Log | None = None) -> str:
    try:
        result = _run(["search", query], timeout=30)
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro search failed: {exc}")
        return ""


def backup(name: str, output: str, compression: str = "zstd", log: Log | None = None) -> bool:
    if log:
        log(f"$ proot-distro backup {name} -o {output} -c {compression}")
    try:
        _run(["backup", name, "-o", output, "-c", compression], timeout=600)
        if log:
            log("done")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro backup failed: {exc}")
        return False


def restore(archive: str, log: Log | None = None) -> bool:
    if log:
        log(f"$ proot-distro restore {archive}")
    try:
        _run(["restore", archive], timeout=600)
        if log:
            log("done")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: proot-distro restore failed: {exc}")
        return False


def login_command(
    name: str,
    command: list[str] | None = None,
    *,
    user: str | None = None,
    shared_tmp: bool = False,
    isolation_preset: isolation.Preset | None = None,
) -> list[str]:
    """Builds (but does not run) the proot-distro login invocation —
    exposed separately so callers (box/user.py, box/packages.py,
    box/create.py) can run it with their own timeout/stdin handling.

    Applies the container's saved isolation preset (isolation.py) by
    default, so every existing caller benefits automatically without
    having to look it up itself — the one exception is iobench.py,
    which passes isolation_preset explicitly to test each candidate in
    turn rather than whatever is currently saved.
    """
    args = [BINARY, "login", name]
    if user:
        args += ["--user", user]
    if shared_tmp:
        args.append("--shared-tmp")
    preset = isolation_preset if isolation_preset is not None else isolation.load_preset(name)
    args += list(preset.flags)
    if command:
        args += ["--", *command]
    return args


def get_proot_cmd(name: str) -> str | None:
    """proot-distro login --get-proot-cmd — prints the assembled proot
    invocation without running it. Useful for Doctor/support output
    (Phase 4)."""
    try:
        result = _run(["login", name, "--get-proot-cmd"], timeout=15)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
