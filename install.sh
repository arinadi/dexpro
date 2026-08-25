#!/data/data/com.termux/files/usr/bin/bash
# dexpro bootstrap — installs git/python/curl if missing, checks out the
# repo, then hands off to install.py for the rest. Mirrors XLabs' two-
# stage install.sh/install.py shape.
set -euo pipefail

REPO_URL="${DEXPRO_REPO_URL:-https://github.com/arinadi/dexpro}"
REPO_DIR="${HOME}/dexpro"

echo ">>> dexpro bootstrap"

pkg install -y git python curl 2>/dev/null || true

if [ -d "$REPO_DIR/.git" ]; then
    echo ">>> dexpro already checked out at $REPO_DIR — pulling latest"
    git -C "$REPO_DIR" pull --ff-only
else
    echo ">>> cloning $REPO_URL"
    git clone "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"
exec python install.py
