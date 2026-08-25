"""dexpro box create — proot-distro install + post-install hooks.

Post-install chain mirrors dextop's container-initialization exactly
(apt update, apt full-upgrade, apt install locales, locale-gen) — that
part of dextop is simple and correct. DNS is a proactive addition:
proot containers don't inherit host DNS automatically (why XLabs ships
a Doctor "DNS" fix); this writes it up front at create time instead of
waiting for a Doctor complaint, using dextop's exact server choice.

`adduser`/`sudo` are installed here too — confirmed on-device (Podman
dev container, `proot-distro install debian:13`) that Docker Hub's
official debian:13 image does NOT ship `adduser` at all ("command not
found"), which would otherwise break box/user.py's add_user() on a
freshly created container. Neither XLabs nor dextop hit this because
neither uses a bare Docker Hub image this way.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from . import manager

Log = Callable[[str], None]

DNS_SERVERS = ("1.1.1.1", "1.0.0.1")  # Cloudflare — dextop's exact choice

INIT_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("apt", "update"),
    ("apt", "full-upgrade", "-y"),
    ("apt", "install", "-y", "locales", "adduser", "sudo"),
    ("locale-gen", "en_US.utf-8"),
)


def dns_config_text() -> str:
    return "\n".join(f"nameserver {server}" for server in DNS_SERVERS) + "\n"


def create(name: str, image: str, log: Log | None = None) -> bool:
    if log:
        log(f"installing {image} as {name}...")
    if not manager.install(image, name, log=log):
        return False

    if not write_dns(name, log=log):
        if log:
            log(
                "warning: DNS setup failed — apt operations inside the "
                "container may fail until fixed manually"
            )

    for command in INIT_COMMANDS:
        if log:
            log(f"running {' '.join(command)}...")
        if not run_in_container(name, list(command), log=log):
            return False
    return True


def write_dns(name: str, log: Log | None = None) -> bool:
    script = f"cat > /etc/resolv.conf << 'DEXPRO_EOF'\n{dns_config_text()}DEXPRO_EOF\n"
    return run_in_container(name, ["sh", "-c", script], log=log)


def run_in_container(name: str, command: list[str], log: Log | None = None) -> bool:
    full = manager.login_command(name, command)
    try:
        subprocess.run(full, capture_output=True, timeout=300, check=True, text=True)
        return True
    except subprocess.CalledProcessError as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc.stderr}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc}")
        return False
