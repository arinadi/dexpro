"""app/native/session.py: generated script content, without executing it.

    python tests/test_session.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app import const
from app.native import gpu, session, x11


def test_script_uses_xfce4_session_not_startxfce4() -> None:
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    check("xfce4-session" in script, "script must launch xfce4-session")
    check(
        "startxfce4" not in script,
        "startxfce4 no-ops when DISPLAY is preset — must not be used",
    )


def test_script_wraps_dbus_launch_conditionally() -> None:
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    check(
        "dbus-launch --exit-with-session xfce4-session" in script,
        "missing conditional dbus-launch wrap",
    )
    check(
        "DBUS_SESSION_BUS_ADDRESS" in script,
        "must check for an existing session bus before wrapping in dbus-launch",
    )


def test_script_sets_display() -> None:
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    check(f"export DISPLAY={x11.DISPLAY}" in script, "DISPLAY not exported correctly")


def test_script_includes_gpu_exports() -> None:
    preset = gpu.preset_by_name("virgl")
    script = session.build_script(preset, pulse_ok=True)
    check("export GALLIUM_DRIVER=virpipe" in script, "GPU preset env vars missing from script")


def test_script_omits_pulse_server_when_audio_unavailable() -> None:
    script = session.build_script(gpu.PRESETS[0], pulse_ok=False)
    check("PULSE_SERVER" not in script, "PULSE_SERVER should be omitted when audio isn't available")


def test_script_pins_xdg_runtime_dir_to_the_shared_constant() -> None:
    # Regression test for a real reported bug: "Test sudah on dan bunyi
    # tapi di XFCE masih belum keluar suara" — the script used to fall
    # back to an independently-guessed XDG_RUNTIME_DIR ("${XDG_RUNTIME_DIR
    # :-$PREFIX/tmp/dexpro-runtime}") instead of the exact same constant
    # audio.py's own PulseAudio calls use, so nothing guaranteed they
    # agreed on where the daemon's socket actually is.
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    check(
        f'export XDG_RUNTIME_DIR="{const.XDG_RUNTIME_DIR}"' in script,
        f"expected the fixed shared constant, got:\n{script}",
    )


def test_script_pulse_server_uses_the_real_pulseaudio_default_path() -> None:
    # PulseAudio's real default socket is $XDG_RUNTIME_DIR/pulse/native —
    # an earlier version of this line went up a directory first
    # ("$XDG_RUNTIME_DIR/../pulse/native"), which never matched.
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    check(
        "unix:$XDG_RUNTIME_DIR/pulse/native" in script,
        f"expected the real PulseAudio default path, got:\n{script}",
    )
    check("/../pulse/native" not in script, f"the wrong relative path is still present:\n{script}")


def test_script_is_shebanged_and_executable_looking() -> None:
    script = session.build_script(gpu.PRESETS[0], pulse_ok=True)
    shebang = "#!/data/data/com.termux/files/usr/bin/bash\n"
    check(script.startswith(shebang), "missing/wrong shebang")


TESTS = [
    test_script_uses_xfce4_session_not_startxfce4,
    test_script_wraps_dbus_launch_conditionally,
    test_script_sets_display,
    test_script_includes_gpu_exports,
    test_script_omits_pulse_server_when_audio_unavailable,
    test_script_pins_xdg_runtime_dir_to_the_shared_constant,
    test_script_pulse_server_uses_the_real_pulseaudio_default_path,
    test_script_is_shebanged_and_executable_looking,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
