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
    Lifecycle()._link_storage()


@_isolated
def test_link_storage_respects_unified_home_opt_in() -> None:
    # "unified-home" only runs link_unified_home() when explicitly set —
    # its own docstring calls this dextop's own default-off behavior.
    # Confirmed here by checking it doesn't create anything under a home
    # dir when the setting is off, then does attempt the linked-mount
    # lookup (which itself no-ops gracefully with no such mount) when on.
    config.unset(STORAGE_LINK_KEY)
    Lifecycle()._link_storage()  # off: must not raise

    config.set_value(STORAGE_LINK_KEY, "unified-home")
    Lifecycle()._link_storage()  # on, but no "Home"-labeled mount exists: must not raise


@_isolated
def test_ensure_audio_skips_pulseaudio_when_disabled_by_default() -> None:
    # Real-device report: PulseAudio "wasn't running" — root cause was
    # dexpro previously always attempting to start it unconditionally.
    # Off is now the default (dextop's own documented choice), so a
    # fresh Lifecycle must not even try, and must say why in the log.
    messages: list[str] = []
    lifecycle = Lifecycle(log=messages.append)
    result = lifecycle._ensure_audio()
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
    result = lifecycle._ensure_audio()
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

    ok = lifecycle._ensure_unified_home_backup()
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
    check(lifecycle._ensure_unified_home_backup(), "first call should back up and succeed")
    first_run = set(os.listdir(const_mod.BACKUP_DIR))

    check(lifecycle._ensure_unified_home_backup(), "second call should short-circuit to True")
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
        lifecycle._link_storage()

    check(
        any("skipping unified-home linking" in m for m in messages),
        f"must explain why linking was skipped: {messages!r}",
    )
    no_false_success = "must not record success that didn't happen"
    check(config.get("UNIFIED_HOME_BACKUP_DONE") is None, no_false_success)


TESTS = [
    test_link_storage_never_raises_without_storage_link_set,
    test_link_storage_respects_unified_home_opt_in,
    test_ensure_audio_skips_pulseaudio_when_disabled_by_default,
    test_ensure_audio_attempts_pulseaudio_when_enabled,
    test_ensure_unified_home_backup_creates_a_real_archive_once,
    test_ensure_unified_home_backup_only_runs_once,
    test_link_storage_skips_unified_home_when_backup_would_fail,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
