"""app/doctor/electron.py: --no-sandbox patching logic, without a real
proot-distro container.

    python tests/test_doctor_electron.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.doctor import electron


def test_resolve_binary_takes_first_token() -> None:
    check(electron.resolve_binary("code %F") == "code", "should strip field codes/args")
    full_path = electron.resolve_binary("/usr/bin/code --foo")
    check(full_path == "/usr/bin/code", "should keep full path")
    check(electron.resolve_binary("") == "", "empty Exec= should resolve to an empty binary")


def test_needs_no_sandbox_patch_true_when_missing() -> None:
    content = "[Desktop Entry]\nExec=code %F\n"
    needs_it = electron.needs_no_sandbox_patch(content)
    check(needs_it, "should need the patch when --no-sandbox is absent")


def test_needs_no_sandbox_patch_false_when_already_present() -> None:
    content = "[Desktop Entry]\nExec=code --no-sandbox %F\n"
    needs_it = electron.needs_no_sandbox_patch(content)
    check(not needs_it, "already-patched Exec= should not be flagged as needing the patch again")


def test_needs_no_sandbox_patch_false_without_exec_line() -> None:
    content = "[Desktop Entry]\nName=Weird\n"
    check(not electron.needs_no_sandbox_patch(content), "no Exec= line means nothing to patch")


def test_patch_no_sandbox_appends_flag() -> None:
    patched = electron.patch_no_sandbox("[Desktop Entry]\nExec=code %F\n")
    check("Exec=code %F --no-sandbox" in patched, f"flag not appended correctly: {patched!r}")


def test_patch_no_sandbox_is_idempotent() -> None:
    once = electron.patch_no_sandbox("[Desktop Entry]\nExec=code %F\n")
    twice = electron.patch_no_sandbox(once)
    check(once == twice, "patching an already-patched file must not duplicate the flag")
    check(twice.count("--no-sandbox") == 1, "must not have two copies of the flag")


def test_is_electron_app_fails_gracefully_when_proot_distro_missing() -> None:
    result = electron.is_electron_app("work", "/usr/share/code/code")
    check(result is False, "should report False, not raise, when proot-distro is unavailable")


def test_scan_and_patch_fails_gracefully_when_proot_distro_missing() -> None:
    result = electron.scan_and_patch("work")
    check(result == [], f"expected an empty list when proot-distro is unavailable, got {result!r}")


def test_find_unpatched_fails_gracefully_when_proot_distro_missing() -> None:
    result = electron.find_unpatched("work")
    check(result == [], f"expected an empty list when proot-distro is unavailable, got {result!r}")


TESTS = [
    test_resolve_binary_takes_first_token,
    test_needs_no_sandbox_patch_true_when_missing,
    test_needs_no_sandbox_patch_false_when_already_present,
    test_needs_no_sandbox_patch_false_without_exec_line,
    test_patch_no_sandbox_appends_flag,
    test_patch_no_sandbox_is_idempotent,
    test_is_electron_app_fails_gracefully_when_proot_distro_missing,
    test_scan_and_patch_fails_gracefully_when_proot_distro_missing,
    test_find_unpatched_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
