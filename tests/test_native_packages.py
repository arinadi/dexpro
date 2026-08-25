"""app/native/packages.py: Termux-side package/repo management, without
a real Termux `pkg`/`dpkg-query` on this dev machine.

    python tests/test_native_packages.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import packages


def test_enabled_repos_reports_a_definite_set_when_dpkg_query_absent() -> None:
    # No dpkg-query on this Windows dev machine — must fail gracefully
    # to "none enabled", not raise.
    result = packages.enabled_repos()
    check(isinstance(result, set), "enabled_repos() must return a set")
    check(result == set(), f"expected no repos detected here, got {result!r}")


def test_enable_repo_rejects_unknown_name_before_touching_the_subprocess() -> None:
    messages: list[str] = []
    result = packages.enable_repo("not-a-real-repo", log=messages.append)
    check(result is False, "must refuse an unlisted repo name")
    check(any("unknown repo" in m for m in messages), f"no rejection reason logged: {messages!r}")


def test_search_rejects_unsafe_term_before_touching_the_subprocess() -> None:
    messages: list[str] = []
    result = packages.search("git; rm -rf /", log=messages.append)
    check(result == [], "must refuse an unsafe search term")
    check(any("unsafe" in m for m in messages), f"no rejection reason logged: {messages!r}")


def test_install_rejects_unsafe_package_name() -> None:
    messages: list[str] = []
    result = packages.install(["ok-name", "bad; rm -rf /"], log=messages.append)
    check(result is False, "must refuse a batch containing an unsafe name")


def test_uninstall_rejects_unsafe_package_name() -> None:
    messages: list[str] = []
    result = packages.uninstall(["$(whoami)"], log=messages.append)
    check(result is False, "must refuse an unsafe name")


def test_search_fails_gracefully_when_apt_cache_missing() -> None:
    # `apt-cache` isn't a real binary on this Windows dev machine either.
    result = packages.search("neovim")
    check(result == [], f"expected an empty list when apt-cache is unavailable, got {result!r}")


def test_search_uses_apt_cache_not_pkg() -> None:
    # Regression test for a real reported bug: `pkg search` prints a
    # "Checking availability of current mirror" preamble to stdout
    # before results (landing as a bogus row in the UI's table) and
    # formats each hit as a multi-line block instead of one line per
    # package (breaking the "first token of the row is the package
    # name" assumption the Store screen relies on — selecting the
    # indented description line installed garbage). apt-cache
    # search --names-only has neither problem and matches what
    # box/packages.py's container-side search() already uses.
    import subprocess
    import unittest.mock as mock

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="neovim - Vim text editor\n", stderr="")

    with mock.patch("subprocess.run", fake_run):
        result = packages.search("neovim")

    check(captured["cmd"][0] == "apt-cache", f"expected apt-cache, got {captured['cmd']!r}")
    not_pkg = "pkg" not in captured["cmd"]
    check(not_pkg, f"must not shell out to the pkg wrapper: {captured['cmd']!r}")
    check(result == ["neovim - Vim text editor"], f"got {result!r}")


TESTS = [
    test_enabled_repos_reports_a_definite_set_when_dpkg_query_absent,
    test_enable_repo_rejects_unknown_name_before_touching_the_subprocess,
    test_search_rejects_unsafe_term_before_touching_the_subprocess,
    test_install_rejects_unsafe_package_name,
    test_uninstall_rejects_unsafe_package_name,
    test_search_fails_gracefully_when_apt_cache_missing,
    test_search_uses_apt_cache_not_pkg,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
