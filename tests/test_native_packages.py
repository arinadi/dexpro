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


def test_ensure_binary_skips_install_when_already_present() -> None:
    import unittest.mock as mock

    install_calls = []

    def fake_install(*args, **kwargs):
        install_calls.append(1)

    with mock.patch.object(packages.shutil, "which", return_value="/usr/bin/git"):
        with mock.patch.object(packages, "install", side_effect=fake_install):
            ok = packages.ensure_binary("git")
    check(ok is True, "must report present without touching install()")
    check(install_calls == [], "must not attempt install when already present")


def test_ensure_binary_installs_and_reverifies_with_which() -> None:
    import unittest.mock as mock

    # Simulate "missing before, present after a successful install" —
    # ensure_binary must re-check shutil.which itself, not trust
    # install()'s own return value as proof the binary landed on PATH.
    which_sequence = iter([None, "/usr/bin/glmark2"])
    with mock.patch.object(packages.shutil, "which", side_effect=lambda name: next(which_sequence)):
        with mock.patch.object(packages, "install", return_value=True):
            ok = packages.ensure_binary("glmark2")
    check(ok is True, "must report available once shutil.which confirms it post-install")


def test_ensure_binary_uses_the_mapped_package_name() -> None:
    import unittest.mock as mock

    calls = []
    with mock.patch.object(packages.shutil, "which", return_value=None):
        with mock.patch.object(
            packages, "install", side_effect=lambda names, log=None: calls.append(names) or False
        ):
            ok = packages.ensure_binary(
                "virgl_test_server_android", package="virglrenderer-android"
            )
    check(ok is False, "install() returning False must propagate as not-available")
    check(calls == [["virglrenderer-android"]], f"expected the mapped package name, got {calls!r}")


def test_ensure_binary_does_not_retry_within_the_same_attempted_set() -> None:
    import unittest.mock as mock

    calls = []
    attempted: set[str] = set()
    with mock.patch.object(packages.shutil, "which", return_value=None):
        with mock.patch.object(
            packages, "install", side_effect=lambda names, log=None: calls.append(names) or False
        ):
            packages.ensure_binary("glmark2", attempted=attempted)
            packages.ensure_binary("glmark2", attempted=attempted)
    check(len(calls) == 1, f"expected exactly one install attempt, got {len(calls)}")


def test_ensure_binary_explains_when_install_succeeds_but_binary_still_missing() -> None:
    # Real device report: "pkg install langsung done tanpa log install,
    # saya curiga lib glmark2 tidak ada di termux" — apt/pkg can exit 0
    # ("done") while never actually providing the binary (e.g. "Unable
    # to locate package" as a non-fatal warning). That contradiction must
    # be explained, not returned as a bare, unexplained False.
    import unittest.mock as mock

    with mock.patch.object(packages.shutil, "which", return_value=None):
        with mock.patch.object(packages, "install", return_value=True):
            messages: list[str] = []
            ok = packages.ensure_binary("glmark2", log=messages.append)
    check(ok is False, "must not report success when the binary still isn't on PATH")
    check(
        any("install reported success" in m and "glmark2" in m for m in messages),
        f"expected the contradiction explained, got {messages!r}",
    )


def test_run_logs_real_output_on_a_successful_install_not_just_done() -> None:
    # A run can exit 0 while still printing something worth seeing (e.g.
    # apt's own "Unable to locate package" as a non-fatal notice) — only
    # ever logging "done" hid that entirely.
    import subprocess
    import unittest.mock as mock

    def fake_run(cmd, **kwargs):
        stdout = "Reading package lists...\nE: Unable to locate package glmark2\n"
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    messages: list[str] = []
    with mock.patch("subprocess.run", fake_run):
        result = packages.install(["glmark2"], log=messages.append)
    check(result is True, "a zero exit code is still reported as success at this layer")
    check(
        any("Unable to locate package glmark2" in m for m in messages),
        f"expected the real apt output surfaced, got {messages!r}",
    )
    check("done" in messages, "must still confirm completion after the output")


def test_ensure_binary_fails_gracefully_with_no_real_pkg() -> None:
    # Real, unmocked behavior on this dev machine: no such binary and no
    # real `pkg` to install it with.
    result = packages.ensure_binary("some-binary-that-does-not-exist-anywhere")
    check(result is False, "must fail gracefully, never raise")


def test_install_logs_the_command_and_success_not_just_failure() -> None:
    # Regression test for a real reported bug: Enable Repo / Install
    # showed a completely empty log window because _run() only ever
    # called log() on failure. A successful command must announce
    # itself and confirm completion, not run silently.
    import subprocess
    import unittest.mock as mock

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    messages: list[str] = []
    with mock.patch("subprocess.run", fake_run):
        result = packages.install(["neovim"], log=messages.append)

    check(result is True, "install should succeed")
    check(any(m.startswith("$ pkg install") for m in messages), f"got {messages!r}")
    check("done" in messages, f"a successful run must confirm completion: {messages!r}")


TESTS = [
    test_enabled_repos_reports_a_definite_set_when_dpkg_query_absent,
    test_enable_repo_rejects_unknown_name_before_touching_the_subprocess,
    test_search_rejects_unsafe_term_before_touching_the_subprocess,
    test_install_rejects_unsafe_package_name,
    test_uninstall_rejects_unsafe_package_name,
    test_search_fails_gracefully_when_apt_cache_missing,
    test_search_uses_apt_cache_not_pkg,
    test_ensure_binary_skips_install_when_already_present,
    test_ensure_binary_installs_and_reverifies_with_which,
    test_ensure_binary_uses_the_mapped_package_name,
    test_ensure_binary_does_not_retry_within_the_same_attempted_set,
    test_ensure_binary_explains_when_install_succeeds_but_binary_still_missing,
    test_run_logs_real_output_on_a_successful_install_not_just_done,
    test_ensure_binary_fails_gracefully_with_no_real_pkg,
    test_install_logs_the_command_and_success_not_just_failure,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
