"""app/doctor/duplicates.py: the protected-package allow-list (a
security-adjacent control — never remove something dexpro itself
needs) and graceful behavior when proot-distro is absent.

    python tests/test_doctor_duplicates.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.doctor import duplicates


def test_protected_packages_are_never_in_the_duplicates_dict() -> None:
    # If a protected package were also in TERMUX_DUPLICATES, Doctor
    # could offer to remove something dexpro itself depends on.
    overlap = duplicates.PROTECTED_TERMUX_PACKAGES & set(duplicates.TERMUX_DUPLICATES)
    check(not overlap, f"protected packages must never appear in TERMUX_DUPLICATES: {overlap!r}")


def test_termux_has_returns_false_for_a_package_that_does_not_exist() -> None:
    result = duplicates.termux_has("this-package-definitely-does-not-exist-xyz")
    check(result is False, "a nonexistent package must report False, not raise")


def test_container_has_fails_gracefully_when_proot_distro_missing() -> None:
    result = duplicates.container_has("work", "node")
    check(result is False, "should report False, not raise, when proot-distro is unavailable")


def test_find_duplicates_never_reports_a_protected_package() -> None:
    # Even if termux_has()/container_has() somehow both returned True
    # for a protected package's binary, find_duplicates() must still
    # exclude it via the `continue` guard, not just rely on the dict
    # not overlapping.
    result = duplicates.find_duplicates("work")
    protected_hit = [p for p in result if p in duplicates.PROTECTED_TERMUX_PACKAGES]
    check(not protected_hit, f"a protected package leaked into duplicates: {protected_hit!r}")


def test_remove_termux_duplicates_refuses_non_allow_listed_packages() -> None:
    messages: list[str] = []
    result = duplicates.remove_termux_duplicates(["python"], log=messages.append)
    check(result is False, "must refuse to remove a protected package even if asked")
    check(any("refusing" in m for m in messages), "no refusal reason logged")


def test_remove_termux_duplicates_refuses_unknown_packages() -> None:
    messages: list[str] = []
    result = duplicates.remove_termux_duplicates(["not-a-tracked-package"], log=messages.append)
    check(result is False, "must refuse a package that isn't in the allow-list at all")
    check(any("refusing" in m for m in messages), "no refusal reason logged")


TESTS = [
    test_protected_packages_are_never_in_the_duplicates_dict,
    test_termux_has_returns_false_for_a_package_that_does_not_exist,
    test_container_has_fails_gracefully_when_proot_distro_missing,
    test_find_duplicates_never_reports_a_protected_package,
    test_remove_termux_duplicates_refuses_non_allow_listed_packages,
    test_remove_termux_duplicates_refuses_unknown_packages,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
