"""app/box/packages.py: SAFE_TERM allow-list (the shell-injection
defense — this is a security control, test it like one) and graceful
behavior when proot-distro is absent.

    python tests/test_box_packages.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import packages


def test_safe_term_accepts_normal_package_names() -> None:
    for name in ("git", "python3", "build-essential", "fd-find", "libssl1.1"):
        check(packages.is_safe_term(name), f"{name!r} should be accepted")


def test_safe_term_rejects_shell_metacharacters() -> None:
    unsafe_names = (
        "git; rm -rf /",
        "git && whoami",
        "$(whoami)",
        "`whoami`",
        "git|cat",
        "../../etc/passwd",
        "",
    )
    for name in unsafe_names:
        check(not packages.is_safe_term(name), f"{name!r} should be rejected")


def test_safe_term_rejects_uppercase_and_leading_punctuation() -> None:
    check(not packages.is_safe_term("Git"), "uppercase rejected — apt package names are lowercase")
    check(not packages.is_safe_term("-git"), "leading hyphen should be rejected")
    check(not packages.is_safe_term(".git"), "leading dot should be rejected")


def test_curated_packages_are_all_safe_terms() -> None:
    unsafe = [p for p in packages.CURATED_PACKAGES if not packages.is_safe_term(p)]
    check(not unsafe, f"curated list contains terms that would be rejected: {unsafe!r}")


def test_install_rejects_unsafe_names_before_touching_the_subprocess() -> None:
    messages: list[str] = []
    result = packages.install("test", ["git", "rm -rf /"], log=messages.append)
    check(result is False, "install() must refuse a batch containing an unsafe name")
    check(any("unsafe" in m for m in messages), "no rejection reason logged")


def test_search_fails_gracefully_when_proot_distro_missing() -> None:
    result = packages.search("test", "git")
    check(result == [], f"expected an empty list when proot-distro is unavailable, got {result!r}")


TESTS = [
    test_safe_term_accepts_normal_package_names,
    test_safe_term_rejects_shell_metacharacters,
    test_safe_term_rejects_uppercase_and_leading_punctuation,
    test_curated_packages_are_all_safe_terms,
    test_install_rejects_unsafe_names_before_touching_the_subprocess,
    test_search_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
