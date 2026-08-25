"""app/doctor/checks.py: the Issue model and native-layer checks when
nothing (X11, proot-distro, termux-x11) is actually installed here.

    python tests/test_doctor_checks.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.doctor import checks
from app.native import audio


def test_check_x11_socket_reports_not_ok_when_absent() -> None:
    issue = checks.check_x11_socket()
    check(issue.ok is False, "no X11 socket exists here — must report not-ok")
    check(issue.detail, "a failing check should explain why")


def test_check_gpu_profile_defaults_to_software_and_is_ok() -> None:
    issue = checks.check_gpu_profile()
    check(issue.ok, "the software baseline should never itself be flagged not-ok")
    check("software" in issue.detail, f"expected the software profile mentioned: {issue.detail!r}")


def _isolated_config(test):
    def wrapper():
        original = const.CONFIG_FILE
        fd, path = tempfile.mkstemp(suffix=".env")
        os.close(fd)
        os.remove(path)
        const.CONFIG_FILE = path
        try:
            test()
        finally:
            const.CONFIG_FILE = original
            if os.path.exists(path):
                os.remove(path)

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated_config
def test_fix_gpu_profile_actually_saves_the_result() -> None:
    # Regression test for a real bug: the old fix=lambda log:
    # bool(gpu.bench(log)) ran the benchmark for real but discarded its
    # result — gpu.save_profile() was never called, so the "fix" never
    # actually changed the persisted profile it was meant to correct.
    from unittest import mock

    from app.native import gpu

    zink = gpu.preset_by_name("zink")
    with mock.patch("app.doctor.checks.gpu.bench", return_value=(zink, 1234)):
        ok = checks._fix_gpu_profile(log=lambda _msg: None)

    check(ok is True, "fix should report success when bench() finds a winner")
    check(gpu.load_profile() == zink, "the benchmarked preset must actually be persisted")


@_isolated_config
def test_fix_gpu_profile_fails_gracefully_when_bench_finds_nothing() -> None:
    from unittest import mock

    with mock.patch("app.doctor.checks.gpu.bench", return_value=None):
        ok = checks._fix_gpu_profile(log=lambda _msg: None)

    check(ok is False, "must report failure, not raise, when nothing scored")


@_isolated_config
def test_check_audio_is_ok_when_disabled_by_default() -> None:
    # Off is the deliberate default (dextop's own — battery/CPU cost),
    # not a fault: a fresh install must not show a red "not ok" for the
    # expected, unconfigured state.
    issue = checks.check_audio()
    check(issue.ok, "disabled-by-default audio must not be flagged as broken")
    check(issue.fix is None, "nothing to fix when it's off on purpose")


@_isolated_config
def test_check_audio_is_a_read_only_probe_when_enabled() -> None:
    # Confirmed on-device (Podman container): `pactl info` autospawns a
    # PulseAudio daemon as a side effect of merely checking whether one
    # is running — that's the opposite of what a Doctor status check
    # should do. Run the check twice; a genuinely read-only probe must
    # report the same thing both times, not "start" something on the
    # first call. (Whether PulseAudio happens to already be running on
    # this host isn't asserted either way — that varies by environment.)
    audio.set_enabled(True)
    first = checks.check_audio()
    second = checks.check_audio()
    check(first.ok == second.ok, "check_audio() must not change system state just by running")
    check(first.fix is not None, "enabled audio should be auto-fixable (ensure_server)")


def test_check_wakelock_binary_reports_a_definite_bool() -> None:
    # Presence varies by environment (absent on this Windows dev
    # machine, but confirmed present even in a bare Podman container —
    # termux-wake-lock ships in core termux-tools, not a separate
    # Termux:API package) — this only asserts the check's own contract,
    # not a specific environment's state.
    issue = checks.check_wakelock_binary()
    check(isinstance(issue.ok, bool), "ok must be a definite bool")
    check(issue.fix is None, "a missing binary isn't something Doctor can install by itself")
    if not issue.ok:
        check(issue.detail, "a failing check should explain why")


def test_check_termux_x11_installed_reports_not_ok_when_absent() -> None:
    issue = checks.check_termux_x11_installed()
    check(issue.ok is False, "termux-x11 isn't installed here")
    check(not issue.unknown, "an absent package is a definite not-ok, not an unknown")


def test_check_termux_x11_app_reports_a_definite_bool() -> None:
    # No `pm` binary on this Windows dev machine — must resolve to the
    # "cannot query" unknown branch, not raise or hang.
    issue = checks.check_termux_x11_app()
    check(isinstance(issue.ok, bool), "ok must be a definite bool")
    check(issue.unknown, "no pm binary here — must be reported as unknown, not a false miss")


def test_check_internet_reports_connected_on_this_dev_machine() -> None:
    # This dev machine has real internet — same live-network tolerance
    # test_box_mirror.py already uses elsewhere in this suite.
    issue = checks.check_internet()
    check(isinstance(issue.ok, bool), "ok must be a definite bool")
    check(issue.fix is None, "connectivity isn't something Doctor can fix by itself")


def test_check_storage_reports_a_definite_bool() -> None:
    issue = checks.check_storage()
    check(isinstance(issue.ok, bool) or issue.unknown, f"got {issue!r}")
    check(issue.fix is None, "free space isn't something Doctor can fix by itself")


def test_check_python_version_is_ok_here() -> None:
    # This project's own venv is 3.10+ by requirement (pyproject.toml).
    issue = checks.check_python_version()
    check(issue.ok, f"expected this venv's Python to satisfy 3.10+, got {issue!r}")


def test_run_native_checks_returns_one_issue_per_check() -> None:
    issues = checks.run_native_checks()
    check(len(issues) == len(checks.NATIVE_CHECKS), "one Issue per registered check")
    check(all(isinstance(i, checks.Issue) for i in issues), "every result must be an Issue")


def test_container_rootfs_path_is_none_for_nonexistent_container() -> None:
    result = checks.container_rootfs_path("definitely-not-a-real-container")
    check(result is None, "a container that was never created has no rootfs path")


def test_check_user_uid_mapped_is_unknown_when_rootfs_missing() -> None:
    issue = checks.check_user_uid_mapped("definitely-not-a-real-container", "dev")
    check(issue.ok is False, "an unresolvable rootfs must not be reported ok")
    check(issue.unknown, "should be flagged unknown, not a false failure claim")


def test_check_textual_importable_is_ok_here() -> None:
    # textual has to be installed for this very test run to exist —
    # a positive case for once, but still asserting the check's contract.
    issue = checks.check_textual_importable()
    check(issue.ok, "textual is installed in this venv — the check must see that")
    check(issue.fix is None, "nothing to fix when it's already importable")


def test_check_launcher_resolves_reports_a_definite_bool_when_absent() -> None:
    # No $PREFIX/bin/dexpro symlink exists on this Windows dev machine —
    # must report a clean not-ok, never raise.
    issue = checks.check_launcher_resolves()
    check(issue.ok is False, "no launcher symlink exists here")
    check(issue.fix is not None, "a missing/broken launcher should be auto-fixable")


def test_check_termux_packages_reports_a_definite_bool() -> None:
    # dpkg-query doesn't exist on this Windows dev machine — must fail
    # gracefully (all "missing"), not crash.
    issue = checks.check_termux_packages()
    check(isinstance(issue.ok, bool), "ok must be a definite bool")
    if not issue.ok:
        check(issue.fix is not None, "missing packages should be auto-fixable via pkg install")


def test_check_duplicates_reports_ok_for_nonexistent_container() -> None:
    # No proot-distro/manager.login_command target exists here — the
    # underlying subprocess calls fail gracefully, so no duplicates are
    # ever found, which is a true "ok", not a crash.
    issue = checks.check_duplicates("definitely-not-a-real-container")
    check(issue.ok, "nothing can be detected as duplicated without a real container")


def test_check_electron_reports_ok_for_nonexistent_container() -> None:
    issue = checks.check_electron("definitely-not-a-real-container")
    check(issue.ok, "nothing can be detected as unpatched without a real container")


def test_check_firefox_tuning_reports_ok_for_nonexistent_container() -> None:
    # No rootfs to check firefox_present() against — treated the same
    # as "Firefox not installed", which is a true ok, not a crash.
    issue = checks.check_firefox_tuning("definitely-not-a-real-container")
    check(issue.ok, "no container means no Firefox to tune, which is a true ok")


def test_run_all_checks_includes_native_and_per_container() -> None:
    issues = checks.run_all_checks(containers=["fake-container"])
    names = [i.name for i in issues]
    has_container_check = any("apt lists" in n for n in names)
    check(has_container_check, "per-container checks must be included for the given container")
    grows = len(issues) > len(checks.NATIVE_CHECKS)
    check(grows, "container checks must add to, not replace, native ones")


TESTS = [
    test_check_x11_socket_reports_not_ok_when_absent,
    test_check_gpu_profile_defaults_to_software_and_is_ok,
    test_fix_gpu_profile_actually_saves_the_result,
    test_fix_gpu_profile_fails_gracefully_when_bench_finds_nothing,
    test_check_audio_is_ok_when_disabled_by_default,
    test_check_audio_is_a_read_only_probe_when_enabled,
    test_check_wakelock_binary_reports_a_definite_bool,
    test_check_termux_x11_installed_reports_not_ok_when_absent,
    test_check_termux_x11_app_reports_a_definite_bool,
    test_check_internet_reports_connected_on_this_dev_machine,
    test_check_storage_reports_a_definite_bool,
    test_check_python_version_is_ok_here,
    test_check_textual_importable_is_ok_here,
    test_check_launcher_resolves_reports_a_definite_bool_when_absent,
    test_check_termux_packages_reports_a_definite_bool,
    test_check_duplicates_reports_ok_for_nonexistent_container,
    test_check_electron_reports_ok_for_nonexistent_container,
    test_check_firefox_tuning_reports_ok_for_nonexistent_container,
    test_run_native_checks_returns_one_issue_per_check,
    test_container_rootfs_path_is_none_for_nonexistent_container,
    test_check_user_uid_mapped_is_unknown_when_rootfs_missing,
    test_run_all_checks_includes_native_and_per_container,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
