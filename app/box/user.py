"""Host-UID/GID-mapped real container user creation — new work, not a
port (build-task-phase2.md Task 3). proot-distro's `--user` flag is
ptrace UID-faking via --change-id, not a real container account;
dextop's own automated path hardcodes 1000:1000, which doesn't map to
the actual host UID either — this is a gap in both reference projects.

Uses os.getuid()/os.getgid(), which only exist on POSIX — this module's
UID-resolving functions cannot run on Windows (there is nothing to map
to there); tested on Linux (Podman dev container) and the real device.

Confirmed on-device: `proot-distro install` pre-populates /etc/passwd
with Android's standard `aid_*` UID table (e.g. `aid_system:1000:1000`)
as part of its own "Registering Android-specific UIDs and GIDs" step —
a plain `adduser --uid <host_uid>` collides ("UID is not unique")
whenever the host UID matches one of those reserved entries. Handled by
checking for an existing aid_* placeholder at that UID first and
rewriting /etc/passwd directly to repurpose it (see
rename_placeholder_script's docstring for why `usermod --login` itself
doesn't work here) instead of creating a conflicting new entry; a
collision with anything else (a real, non-placeholder account) is
treated as a hard failure rather than silently overwritten.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from . import manager

Log = Callable[[str], None]


def adduser_command(uid: int, gid: int, username: str) -> list[str]:
    return [
        "adduser",
        "--uid",
        str(uid),
        "--gid",
        str(gid),
        "--gecos",
        "",
        "--disabled-password",
        username,
    ]


def rename_placeholder_script(existing_name: str, username: str, uid: int, gid: int) -> str:
    """Repurposes an existing `aid_*` placeholder account at the target
    UID into the real dexpro user, instead of colliding with it.

    Confirmed on-device: `usermod --login` refuses this with "user is
    currently used by process 1" — proot has no real UID namespaces, so
    the very shell process running the rename command is itself, at the
    kernel level, running as that UID. usermod's active-user safety
    check isn't a false positive, it's structurally always true under
    proot. A direct, field-based /etc/passwd edit (awk, not usermod) has
    no such check. chown uses the numeric uid:gid, not `username:
    username` — the placeholder's group name (e.g. "system") won't
    generally match the new username.
    """
    home = f"/home/{username}"
    passwd_rewrite = (
        f"awk -F: -v OFS=: -v old={existing_name!r} -v new={username!r} -v home={home!r} "
        "'$1==old { $1=new; $6=home; $7=\"/bin/bash\" } 1' /etc/passwd "
        "> /etc/passwd.dexpro-new && mv /etc/passwd.dexpro-new /etc/passwd"
    )
    shadow_rewrite = (
        f"awk -F: -v OFS=: -v old={existing_name!r} -v new={username!r} "
        "'$1==old { $1=new } 1' /etc/shadow "
        "> /etc/shadow.dexpro-new && mv /etc/shadow.dexpro-new /etc/shadow"
    )
    return (
        f"{passwd_rewrite} && {shadow_rewrite} && "
        f"mkdir -p {home} && chown {uid}:{gid} {home}"
    )


def sudoers_line(username: str) -> str:
    return f"{username} ALL=(ALL) NOPASSWD:ALL"


def find_existing_account(name: str, uid: int, log: Log | None = None) -> str | None:
    """Returns the username already occupying `uid` inside the
    container, or None if the UID is free."""
    script = f"getent passwd {uid} | cut -d: -f1"
    full = manager.login_command(name, ["sh", "-c", script])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15, text=True, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"warning: could not check for an existing account at UID {uid}: {exc}")
        return None
    existing = result.stdout.strip()
    return existing or None


def add_user(name: str, username: str, sudo: bool = False, log: Log | None = None) -> bool:
    import os  # local import: keeps module import-safe on non-POSIX hosts

    uid = os.getuid()
    gid = os.getgid()

    existing = find_existing_account(name, uid, log=log)
    if existing is None:
        created = _run(name, adduser_command(uid, gid, username), log=log)
    elif existing.startswith("aid_"):
        if log:
            log(f"UID {uid} is taken by proot-distro's placeholder '{existing}' — repurposing it")
        script = rename_placeholder_script(existing, username, uid, gid)
        created = _run(name, ["sh", "-c", script], log=log)
    else:
        if log:
            log(
                f"error: UID {uid} is already a real account ('{existing}') inside "
                f"'{name}' — refusing to overwrite it"
            )
        return False

    if not created:
        return False

    if sudo:
        if not _run(name, ["usermod", "-aG", "sudo", username], log=log):
            return False
        script = f"echo '{sudoers_line(username)}' > /etc/sudoers.d/{username}"
        if not _run(name, ["sh", "-c", script], log=log):
            return False

    runtime_dir = f"/run/user/{uid}"
    if not _run(name, ["mkdir", "-p", runtime_dir], log=log):
        return False
    return _run(name, ["chmod", "700", runtime_dir], log=log)


def owner_matches_host(path: str, log: Log | None = None) -> bool:
    """Doctor-style check (build-task-phase2.md Task 5's own test,
    reused by Phase 4's standing Doctor check): does a file at `path`
    (a host-visible path into the container's rootfs) actually show the
    real host UID? This is the actual pass/fail signal for "host-UID-
    mapped" working — not just "user creation didn't error." """
    import os

    try:
        return os.stat(path).st_uid == os.getuid()
    except OSError as exc:
        if log:
            log(f"error: could not stat {path}: {exc}")
        return False


def _run(name: str, command: list[str], log: Log | None) -> bool:
    full = manager.login_command(name, command)
    try:
        subprocess.run(full, capture_output=True, timeout=60, check=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc.stderr}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc}")
        return False
