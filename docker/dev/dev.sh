#!/data/data/com.termux/files/usr/bin/bash
# ═══════════════════════════════════════════════════════════════
# dexpro Dev — Docker/Podman development wrapper
#  Usage: dev.sh [start|shell|stop|status]
#
#  Deliberately has NO proot-distro layer, unlike XLabs' own dev.sh —
#  that's the entire point of Phase 1's native session: xfce4-session
#  launches directly against the host-forwarded DISPLAY (WSLg or a Linux
#  X server), the same way app/native/session.py's generated script does
#  on a real device, just without termux-x11/proot in between.
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

cmd_start() {
    echo ">>> Starting native XFCE session..."
    echo "  Display: $DISPLAY"
    export NO_AT_BRIDGE=1
    export LIBGL_ALWAYS_SOFTWARE=1
    rm -f /tmp/dbus-* 2>/dev/null || true
    pulseaudio --start --exit-idle-time=-1 2>/dev/null || true
    dbus-launch --exit-with-session xfce4-session
}

cmd_shell() {
    echo ">>> Interactive shell..."
    bash
}

cmd_stop() {
    echo ">>> Stopping XFCE session..."
    pkill -f xfce4-session 2>/dev/null || true
    pkill -f dbus-launch 2>/dev/null || true
    echo "  done"
}

cmd_status() {
    if pgrep -f xfce4-session >/dev/null 2>&1; then
        echo "XFCE: running"
    else
        echo "XFCE: not running"
    fi
}

cmd_help() {
    echo "dexpro Dev — Docker/Podman development environment"
    echo ""
    echo "Usage: dev.sh <command>"
    echo ""
    echo "Commands:"
    echo "  start    Launch a native XFCE session (no proot) against the host DISPLAY"
    echo "  shell    Enter an interactive shell"
    echo "  stop     Stop the XFCE session"
    echo "  status   Show session status"
    echo ""
    echo "Host requirements (Windows + WSLg):"
    echo "  - Podman Desktop or Docker Desktop installed"
    echo "  - WSLg enabled (Windows 11) — X11 auto-forwarded"
    echo ""
    echo "Host requirements (Linux/Mac):"
    echo "  - VcXsrv or X410 running (Display :0)"
    echo "  - export DISPLAY=:0"
    echo ""
    echo "NOT exercised by this harness — needs the real phone:"
    echo "  termux-wake-lock, real termux-x11 app pairing, actual device"
    echo "  GPU acceleration (Adreno/Mali), Samsung DeX docking."
    echo "  See build-task-phase1.md's spike table."
}

case "${1:-help}" in
    start)  cmd_start ;;
    shell)  cmd_shell ;;
    stop)   cmd_stop ;;
    status) cmd_status ;;
    help|*) cmd_help ;;
esac
