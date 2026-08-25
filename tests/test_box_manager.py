"""app/box/manager.py: version parsing, command construction, and
graceful behavior when proot-distro is absent (true on this dev machine
— proot-distro is Termux/Android-only).

    python tests/test_box_manager.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import manager


def test_parse_version_extracts_semver() -> None:
    check(manager.parse_version("proot-distro 5.8.0") == (5, 8, 0), "did not extract 5.8.0")
    check(manager.parse_version("v5.8.0-dev") == (5, 8, 0), "did not tolerate a prefix/suffix")
    check(manager.parse_version("nonsense") is None, "should not extract a version from garbage")


def test_check_version_fails_closed_when_binary_missing() -> None:
    messages: list[str] = []
    result = manager.check_version(log=messages.append)
    check(result is False, "check_version should fail when proot-distro isn't installed")
    check(any("not found" in m for m in messages), "no warning logged for a missing binary")


def test_check_version_rejects_old_versions() -> None:
    # 4.9.9 < MIN_VERSION (5.0.0) — this must be caught even though the
    # binary check_version() would actually shell out to isn't present
    # here; parse_version()/the comparison is what's under test.
    old_version = manager.parse_version("proot-distro 4.9.9")
    check(old_version < manager.MIN_VERSION, "version compare is wrong")


def test_login_command_construction() -> None:
    cmd = manager.login_command("work")
    check(cmd == ["proot-distro", "login", "work"], f"unexpected bare login command: {cmd}")

    cmd = manager.login_command("work", ["echo", "hi"], user="dev", shared_tmp=True)
    check(cmd[:3] == ["proot-distro", "login", "work"], "wrong command prefix")
    check("--user" in cmd and "dev" in cmd, "user flag missing")
    check("--shared-tmp" in cmd, "shared-tmp flag missing")
    check(cmd[-3:] == ["--", "echo", "hi"], "trailing command not appended correctly")


def test_list_containers_returns_empty_list_when_binary_missing() -> None:
    result = manager.list_containers()
    check(result == [], f"expected an empty list, got {result!r}")


def test_install_and_remove_report_failure_gracefully_when_binary_missing() -> None:
    messages: list[str] = []
    check(manager.install("debian:13", "test", log=messages.append) is False, "install should fail")
    check(manager.remove("test", log=messages.append) is False, "remove should fail")


TESTS = [
    test_parse_version_extracts_semver,
    test_check_version_fails_closed_when_binary_missing,
    test_check_version_rejects_old_versions,
    test_login_command_construction,
    test_list_containers_returns_empty_list_when_binary_missing,
    test_install_and_remove_report_failure_gracefully_when_binary_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
