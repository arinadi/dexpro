#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  dexpro TUI Test Script (Podman)
#
#  Purpose: Run dexpro's unit test suite inside a Termux-shaped
#           container, so it exercises real `pkg`-installed Python
#           rather than whatever Python happens to be on the dev PC.
#  Usage: bash test-tui.sh
#
#  NOTE: This is for LOCAL TESTING ONLY. Actual install happens on
#        Android (Termux).
#
#  What this tests:
#    - dexpro's unit test suite (tests/run_tests.py)
#    - TUI navigation (headless, via Textual's Pilot — no real X11 needed)
#
#  What this does NOT test:
#    - Actual desktop launch (use docker/dev/dev.sh for that, with
#      WSLg/X server passthrough — see its --help)
#    - termux-wake-lock, real termux-x11 app pairing, actual device GPU
#      acceleration, Samsung DeX docking — those need the real phone
# ═══════════════════════════════════════════════════════════════
set -e

IMAGE="dexpro-dev"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# On Windows (Git Bash / MSYS), convert to Windows path for Podman
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
    PROJECT_DIR="$(cygpath -w "$PROJECT_DIR")"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  dexpro TUI Test (Podman)"
echo "═══════════════════════════════════════════"
echo ""

if ! command -v podman &>/dev/null; then
    echo "✗ Podman not found. Install: https://podman-desktop.io/"
    exit 1
fi

if ! podman machine info &>/dev/null; then
    echo ">>> Starting Podman machine..."
    podman machine init 2>/dev/null || true
    podman machine start
fi

echo ">>> Building dev container..."
podman build -t "$IMAGE" -f docker/dev/Dockerfile docker/dev

echo ""
echo ">>> Running test suite..."
echo "    (Project mounted at /data/data/com.termux/files/home/dexpro)"
echo ""

podman run -it --rm \
    -v "${PROJECT_DIR}:/data/data/com.termux/files/home/dexpro" \
    "$IMAGE" bash -c "
        cd /data/data/com.termux/files/home/dexpro
        pip install textual --quiet --break-system-packages 2>/dev/null || \
        pip install textual --quiet --user 2>/dev/null || true
        python3 tests/run_tests.py
    "
