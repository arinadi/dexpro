"""Native desktop session launch script — no proot-distro wrapper, runs
directly as the Termux user.

Explicitly uses ``xfce4-session`` rather than ``startxfce4``, matching
XLabs' reasoning: ``startxfce4`` no-ops when DISPLAY is already set
(prints "X server already running", hands off to xinitrc, session never
actually launches). Wraps in ``dbus-launch --exit-with-session`` only if
``DBUS_SESSION_BUS_ADDRESS`` is unset — shared prior art with both XLabs
and dextop's ``container_session()``, not proot-specific.

Deliberately does NOT pre-implement XLabs' ``.ICE-unix`` ownership
workaround (``prepare_ice_dir``) — that fix exists specifically because
proot mis-reports file ownership, which doesn't apply once there's no
proot in this path. See the Phase 1 spike table before adding it back.
"""

from __future__ import annotations

from . import gpu, x11

_SHEBANG = "#!/data/data/com.termux/files/usr/bin/bash"


def build_script(preset: gpu.Preset, pulse_ok: bool) -> str:
    lines = [
        _SHEBANG,
        f"export DISPLAY={x11.DISPLAY}",
        "export NO_AT_BRIDGE=1",
        'XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$PREFIX/tmp/dexpro-runtime}"',
        'mkdir -p "$XDG_RUNTIME_DIR"',
        'chmod 700 "$XDG_RUNTIME_DIR"',
        "export XDG_RUNTIME_DIR",
    ]
    if pulse_ok:
        lines.append('export PULSE_SERVER="${PULSE_SERVER:-unix:$XDG_RUNTIME_DIR/../pulse/native}"')
    lines.extend(gpu.client_exports(preset).splitlines())
    lines.append(
        'if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then\n'
        "    exec dbus-launch --exit-with-session xfce4-session\n"
        "else\n"
        "    exec xfce4-session\n"
        "fi"
    )
    return "\n".join(lines) + "\n"
