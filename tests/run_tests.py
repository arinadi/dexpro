#!/usr/bin/env python3
"""Run every dexpro test module together.

Tests are split by module (test_gpu.py, test_session.py, ...) — see
tests/support.py for the shared check()/run() helpers. This file just
collects each module's TESTS list and runs them as one suite.

    python tests/run_tests.py           # everything
    python tests/test_gpu.py            # just one module, while working on it
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import support
from test_action_screen import TESTS as ACTION_SCREEN_TESTS
from test_android_bridge import TESTS as ANDROID_BRIDGE_TESTS
from test_android_storage import TESTS as ANDROID_STORAGE_TESTS
from test_audio import TESTS as AUDIO_TESTS
from test_backup import TESTS as BACKUP_TESTS
from test_backup_screen import TESTS as BACKUP_SCREEN_TESTS
from test_box_browser import TESTS as BOX_BROWSER_TESTS
from test_box_create import TESTS as BOX_CREATE_TESTS
from test_box_export import TESTS as BOX_EXPORT_TESTS
from test_box_iobench import TESTS as BOX_IOBENCH_TESTS
from test_box_isolation import TESTS as BOX_ISOLATION_TESTS
from test_box_manager import TESTS as BOX_MANAGER_TESTS
from test_box_manager_screen import TESTS as BOX_MANAGER_SCREEN_TESTS
from test_box_mirror import TESTS as BOX_MIRROR_TESTS
from test_box_packages import TESTS as BOX_PACKAGES_TESTS
from test_box_user import TESTS as BOX_USER_TESTS
from test_config import TESTS as CONFIG_TESTS
from test_doctor_checks import TESTS as DOCTOR_CHECKS_TESTS
from test_doctor_duplicates import TESTS as DOCTOR_DUPLICATES_TESTS
from test_doctor_electron import TESTS as DOCTOR_ELECTRON_TESTS
from test_doctor_fonts import TESTS as DOCTOR_FONTS_TESTS
from test_doctor_screen import TESTS as DOCTOR_SCREEN_TESTS
from test_export_screen import TESTS as EXPORT_SCREEN_TESTS
from test_gpu import TESTS as GPU_TESTS
from test_lifecycle import TESTS as LIFECYCLE_TESTS
from test_main_screen import TESTS as MAIN_SCREEN_TESTS
from test_native_packages import TESTS as NATIVE_PACKAGES_TESTS
from test_proc import TESTS as PROC_TESTS
from test_session import TESTS as SESSION_TESTS
from test_settings_screen import TESTS as SETTINGS_SCREEN_TESTS
from test_store_screen import TESTS as STORE_SCREEN_TESTS
from test_termux_appearance import TESTS as TERMUX_APPEARANCE_TESTS
from test_termux_store_screen import TESTS as TERMUX_STORE_SCREEN_TESTS
from test_wakelock import TESTS as WAKELOCK_TESTS
from test_x11 import TESTS as X11_TESTS

# Low-level helpers first, TUI last — not load-bearing, just easier to
# read a failed run top to bottom.
ALL_TESTS = [
    *CONFIG_TESTS,
    *WAKELOCK_TESTS,
    *PROC_TESTS,
    *AUDIO_TESTS,
    *GPU_TESTS,
    *X11_TESTS,
    *SESSION_TESTS,
    *LIFECYCLE_TESTS,
    *BOX_MANAGER_TESTS,
    *BOX_CREATE_TESTS,
    *BOX_USER_TESTS,
    *BOX_PACKAGES_TESTS,
    *BOX_EXPORT_TESTS,
    *BOX_ISOLATION_TESTS,
    *BOX_IOBENCH_TESTS,
    *BOX_BROWSER_TESTS,
    *BOX_MIRROR_TESTS,
    *NATIVE_PACKAGES_TESTS,
    *DOCTOR_CHECKS_TESTS,
    *DOCTOR_ELECTRON_TESTS,
    *DOCTOR_DUPLICATES_TESTS,
    *DOCTOR_FONTS_TESTS,
    *BACKUP_TESTS,
    *ANDROID_STORAGE_TESTS,
    *ANDROID_BRIDGE_TESTS,
    *ACTION_SCREEN_TESTS,
    *MAIN_SCREEN_TESTS,
    *BOX_MANAGER_SCREEN_TESTS,
    *EXPORT_SCREEN_TESTS,
    *DOCTOR_SCREEN_TESTS,
    *BACKUP_SCREEN_TESTS,
    *SETTINGS_SCREEN_TESTS,
    *STORE_SCREEN_TESTS,
    *TERMUX_APPEARANCE_TESTS,
    *TERMUX_STORE_SCREEN_TESTS,
]


def main() -> int:
    return support.run(ALL_TESTS)


if __name__ == "__main__":
    sys.exit(main())
