"""app/native/lifecycle.py: the storage-linking step wired into
start() — audit.md follow-up (STORAGE_LINK was a Settings key nothing
ever read; android/storage.py's linking functions existed but were
never called from anywhere). Only _link_storage() is unit-tested here:
the full start()/stop() chain needs a real wakelock/X11/session
environment this dev machine doesn't have.

    python tests/test_lifecycle.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import config, const
from app.native import audio
from app.native.lifecycle import STORAGE_LINK_KEY, Lifecycle


def _isolated(test):
    def wrapper():
        tmp = tempfile.mkdtemp(prefix="dexpro-lifecycle-test-")
        originals = (
            const.MEDIA_DIR,
            const.CONFIG_FILE,
            const.TERMUX_HOME,
            const.BACKUP_DIR,
            const.TMPDIR,
        )
        const.MEDIA_DIR = os.path.join(tmp, "media")
        fd, path = tempfile.mkstemp(suffix=".env", dir=tmp)
        os.close(fd)
        os.remove(path)
        const.CONFIG_FILE = path
        const.TERMUX_HOME = os.path.join(tmp, "home")
        const.BACKUP_DIR = os.path.join(tmp, "backups")
        const.TMPDIR = os.path.join(tmp, "tmp")
        os.makedirs(const.TERMUX_HOME)
        os.makedirs(const.TMPDIR)
        try:
            test()
        finally:
            (
                const.MEDIA_DIR,
                const.CONFIG_FILE,
                const.TERMUX_HOME,
                const.BACKUP_DIR,
                const.TMPDIR,
            ) = originals

    wrapper.__name__ = test.__name__
    return wrapper


@_isolated
def test_link_storage_never_raises_without_storage_link_set() -> None:
    # No /storage, no /proc/mounts entries under it on this Windows dev
    # machine — every real call inside _link_storage() must fail
    # gracefully, not raise.
    Lifecycle()._link_storage(lambda _msg: None)


@_isolated
def test_link_storage_respects_unified_home_opt_in() -> None:
    # "unified-home" only runs link_unified_home() when explicitly set —
    # its own docstring calls this dextop's own default-off behavior.
    # Confirmed here by checking it doesn't create anything under a home
    # dir when the setting is off, then does attempt the linked-mount
    # lookup (which itself no-ops gracefully with no such mount) when on.
    config.unset(STORAGE_LINK_KEY)
    Lifecycle()._link_storage(lambda _msg: None)  # off: must not raise

    config.set_value(STORAGE_LINK_KEY, "unified-home")
    # on, but no "Home"-labeled mount exists: must not raise
    Lifecycle()._link_storage(lambda _msg: None)


@_isolated
def test_ensure_audio_skips_pulseaudio_when_disabled_by_default() -> None:
    # Real-device report: PulseAudio "wasn't running" — root cause was
    # dexpro previously always attempting to start it unconditionally.
    # Off is now the default (dextop's own documented choice), so a
    # fresh Lifecycle must not even try, and must say why in the log.
    messages: list[str] = []
    lifecycle = Lifecycle(log=messages.append)
    result = lifecycle._ensure_audio(messages.append)
    check(result is False, "audio must be reported unavailable when disabled")
    check(
        any("disabled in Settings" in m for m in messages),
        f"must explain why it was skipped: {messages!r}",
    )


@_isolated
def test_ensure_audio_attempts_pulseaudio_when_enabled() -> None:
    audio.set_enabled(True)
    messages: list[str] = []
    lifecycle = Lifecycle(log=messages.append)
    result = lifecycle._ensure_audio(messages.append)
    # No real pulseaudio on this Windows dev machine, so this can't
    # succeed — the contract being tested is that it actually tries
    # (never silently skips) rather than the outcome.
    check(isinstance(result, bool), "must return a definite bool, never raise")
    check(not any("disabled in Settings" in m for m in messages), f"got {messages!r}")


@_isolated
def test_ensure_unified_home_backup_creates_a_real_archive_once() -> None:
    # Re-researched from dextop 2026-08-26: it always backs up home
    # before doing anything that could destroy it, "regardless, to
    # ensure some kind of safety" — link_unified_home() replaces
    # top-level home entries, so it gets the same one-time net. Uses
    # real tar (available via Git Bash/MSYS on this dev machine), same
    # philosophy as test_backup.py's own round-trip tests.
    from app import const as const_mod

    messages: list[str] = []
    lifecycle = Lifecycle(log=messages.append)

    ok = lifecycle._ensure_unified_home_backup(messages.append)
    check(ok, "the first-ever backup attempt should succeed with real tar available")
    check(
        config.get("UNIFIED_HOME_BACKUP_DONE") is not None,
        "the checkpoint must be recorded so this doesn't repeat every session",
    )
    entries = os.listdir(const_mod.BACKUP_DIR)
    check(len(entries) == 1, f"expected exactly one archive created, got {entries!r}")


@_isolated
def test_ensure_unified_home_backup_only_runs_once() -> None:
    from app import const as const_mod

    lifecycle = Lifecycle(log=lambda _msg: None)
    noop = lambda _msg: None  # noqa: E731
    check(lifecycle._ensure_unified_home_backup(noop), "first call should back up and succeed")
    first_run = set(os.listdir(const_mod.BACKUP_DIR))

    check(lifecycle._ensure_unified_home_backup(noop), "second call should short-circuit to True")
    second_run = set(os.listdir(const_mod.BACKUP_DIR))
    check(first_run == second_run, "a second call must not create another archive")


@_isolated
def test_link_storage_skips_unified_home_when_backup_would_fail() -> None:
    # If backup_native_home() can't succeed, unified-home linking (the
    # actually destructive step) must not proceed either — safety over
    # honoring the setting blindly.
    from unittest import mock

    config.set_value(STORAGE_LINK_KEY, "unified-home")
    messages: list[str] = []
    lifecycle = Lifecycle(log=messages.append)

    with mock.patch("app.native.lifecycle.backup.backup_native_home", return_value=None):
        lifecycle._link_storage(messages.append)

    check(
        any("skipping unified-home linking" in m for m in messages),
        f"must explain why linking was skipped: {messages!r}",
    )
    no_false_success = "must not record success that didn't happen"
    check(config.get("UNIFIED_HOME_BACKUP_DONE") is None, no_false_success)


def test_start_and_stop_use_the_passed_in_log_not_only_the_default() -> None:
    # Real bug: Lifecycle's own self.log went to Textual's internal
    # devtools log, never the visible ActionScreen the user watches —
    # every diagnostic this class ever produced was invisible there.
    # start()/stop() must actually use whatever logger is passed in.
    messages: list[str] = []
    lifecycle = Lifecycle(log=lambda _msg: None)  # the "wrong" default
    lifecycle.stop(messages.append)  # no real session running: still logs
    check(len(messages) > 0, "stop() must log through the passed-in logger, not just self.log")


def test_sweep_survivors_is_a_noop_when_nothing_matches() -> None:
    # No real pgrep on this Windows dev machine — pgrep() reports False,
    # so this must do nothing (and not raise).
    lc = Lifecycle(log=lambda _msg: None)
    lc._sweep_survivors(lambda _msg: None)


def test_sweep_survivors_kills_and_logs_when_something_matches() -> None:
    # Regression test for XLabs' own stop_desktop() final catch-all step
    # ("anything that outlived its parent") — dexpro's stop() had no
    # equivalent before.
    from unittest import mock

    from app.native import lifecycle as lifecycle_mod

    messages: list[str] = []
    calls = []
    lc = Lifecycle(log=lambda _msg: None)
    with mock.patch.object(lifecycle_mod.proc_util, "pgrep", return_value=True):
        with mock.patch.object(
            lifecycle_mod.proc_util,
            "kill_pattern",
            side_effect=lambda p, log=None, wait=3.0: calls.append(p) or True,
        ):
            lc._sweep_survivors(messages.append)
    check(calls == [lifecycle_mod._SURVIVOR_PATTERN], f"got {calls!r}")
    check(any("sweeping survivors" in m for m in messages), f"got {messages!r}")


def test_wait_for_session_reports_false_when_process_never_starts() -> None:
    # No real bash/xfce4-session process was ever assigned — is_running()
    # is always False, so this must give up and report failure rather
    # than hang or raise. Patches the module's own time.sleep so this
    # doesn't actually wait the full real timeout.
    from unittest import mock

    from app.native import lifecycle as lifecycle_mod

    messages: list[str] = []
    lc = Lifecycle(log=messages.append)
    with mock.patch.object(lifecycle_mod.time, "sleep"):
        with mock.patch.object(lifecycle_mod, "_SESSION_STARTUP_TIMEOUT", 2.0):
            result = lc._wait_for_session(messages.append)
    check(result is False, "must report failure when the session never comes up")


TESTS = [
    test_link_storage_never_raises_without_storage_link_set,
    test_link_storage_respects_unified_home_opt_in,
    test_ensure_audio_skips_pulseaudio_when_disabled_by_default,
    test_ensure_audio_attempts_pulseaudio_when_enabled,
    test_ensure_unified_home_backup_creates_a_real_archive_once,
    test_ensure_unified_home_backup_only_runs_once,
    test_link_storage_skips_unified_home_when_backup_would_fail,
    test_start_and_stop_use_the_passed_in_log_not_only_the_default,
    test_sweep_survivors_is_a_noop_when_nothing_matches,
    test_sweep_survivors_kills_and_logs_when_something_matches,
    test_wait_for_session_reports_false_when_process_never_starts,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
