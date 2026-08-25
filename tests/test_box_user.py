"""app/box/user.py: command construction (platform-independent) and the
UID-mapping check (POSIX-only — os.getuid() doesn't exist on Windows,
skipped gracefully here rather than failing on a platform the real
feature was never meant to run on).

    python tests/test_box_user.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import user


def test_adduser_command_uses_real_uid_not_hardcoded_1000() -> None:
    # This is the actual fix over dextop's own automated path, which
    # hardcodes 1000:1000 regardless of the real host UID.
    cmd = user.adduser_command(uid=54321, gid=54321, username="dev")
    check("--uid" in cmd and "54321" in cmd, "UID not passed through correctly")
    check("--gid" in cmd and "54321" in cmd, "GID not passed through correctly")
    check("--disabled-password" in cmd, "missing --disabled-password")
    check(cmd[-1] == "dev", "username should be the last argument")


def test_rename_placeholder_script_repurposes_placeholder() -> None:
    # Confirmed on-device: proot-distro pre-populates /etc/passwd with
    # Android's aid_* UID table (e.g. aid_system:1000:1000) — a naive
    # adduser --uid collides with it whenever the host UID matches one
    # of those entries. Also confirmed on-device: `usermod --login`
    # itself refuses this ("user is currently used by process 1" — true
    # structurally under proot, not a fluke), hence the direct
    # /etc/passwd rewrite tested here instead.
    script = user.rename_placeholder_script("aid_system", "dev", uid=1000, gid=1000)
    check("usermod" not in script, "must not use usermod — confirmed it refuses this under proot")
    check("/etc/passwd" in script, "must rewrite /etc/passwd")
    check("/etc/shadow" in script, "must rewrite /etc/shadow too, or login will break")
    check("aid_system" in script, "must reference the existing placeholder name")
    check("dev" in script, "must reference the new username")
    check("chown 1000:1000" in script, "must chown by numeric uid:gid, not a guessed group name")


def test_sudoers_line_is_nopasswd_all() -> None:
    line = user.sudoers_line("dev")
    check(line.startswith("dev "), "sudoers line doesn't start with the username")
    check("NOPASSWD:ALL" in line, "sudoers line isn't NOPASSWD:ALL")


def test_find_existing_account_returns_none_when_proot_distro_missing() -> None:
    messages: list[str] = []
    result = user.find_existing_account("test", 1000, log=messages.append)
    check(result is None, "should return None, not raise, when proot-distro is unavailable")


def test_owner_matches_host_skips_on_non_posix() -> None:
    if not hasattr(os, "getuid"):
        # Windows: os.getuid() doesn't exist — there is no host UID to
        # map to here, so this is a documented skip, not a failure.
        return
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = f.name
    try:
        owned_by_us = user.owner_matches_host(path)
        check(owned_by_us, "a file this process just created should match its own UID")
    finally:
        os.remove(path)


def test_owner_matches_host_false_for_missing_file() -> None:
    if not hasattr(os, "getuid"):
        return
    result = user.owner_matches_host("/nonexistent/path/for/sure")
    check(result is False, "missing file should report False, not raise")


def test_add_user_fails_gracefully_when_proot_distro_missing() -> None:
    if not hasattr(os, "getuid"):
        # add_user() calls os.getuid() before ever reaching the
        # subprocess call — cannot run on Windows at all.
        return
    messages: list[str] = []
    result = user.add_user("test", "dev", log=messages.append)
    check(result is False, "add_user() should fail when proot-distro isn't installed")


TESTS = [
    test_adduser_command_uses_real_uid_not_hardcoded_1000,
    test_rename_placeholder_script_repurposes_placeholder,
    test_sudoers_line_is_nopasswd_all,
    test_find_existing_account_returns_none_when_proot_distro_missing,
    test_owner_matches_host_skips_on_non_posix,
    test_owner_matches_host_false_for_missing_file,
    test_add_user_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
