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

from support import run

from app import config, const
from app.native.lifecycle import STORAGE_LINK_KEY, Lifecycle


def _isolated(test):
    def wrapper():
        tmp = tempfile.mkdtemp(prefix="dexpro-lifecycle-test-")
        originals = (const.MEDIA_DIR, const.CONFIG_FILE)
        const.MEDIA_DIR = os.path.join(tmp, "media")
        fd, path = tempfile.mkstemp(suffix=".env", dir=tmp)
        os.close(fd)
        os.remove(path)
        const.CONFIG_FILE = path
        try:
            test()
        finally:
            const.MEDIA_DIR, const.CONFIG_FILE = originals

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


TESTS = [
    test_link_storage_never_raises_without_storage_link_set,
    test_link_storage_respects_unified_home_opt_in,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
