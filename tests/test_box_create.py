"""app/box/create.py: DNS config content and init command shape, without
actually running proot-distro.

    python tests/test_box_create.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import create


def test_dns_config_uses_cloudflare_matching_dextop() -> None:
    text = create.dns_config_text()
    check("nameserver 1.1.1.1" in text, "missing primary Cloudflare DNS")
    check("nameserver 1.0.0.1" in text, "missing secondary Cloudflare DNS")


def test_init_commands_match_dextop_container_initialization() -> None:
    commands = [" ".join(c) for c in create.INIT_COMMANDS]
    check("apt update" in commands, "missing apt update")
    check(any(c.startswith("apt full-upgrade") for c in commands), "missing apt full-upgrade")
    check(any("locales" in c for c in commands), "missing locales install")
    check(any(c.startswith("locale-gen") for c in commands), "missing locale-gen")


def test_init_commands_install_adduser_and_sudo() -> None:
    # Confirmed on-device: Docker Hub's official debian:13 image doesn't
    # ship adduser at all — box/user.py's add_user() would fail on a
    # freshly created container without this.
    commands = [" ".join(c) for c in create.INIT_COMMANDS]
    check(any("adduser" in c for c in commands), "adduser must be installed during create()")
    check(any("sudo" in c for c in commands), "sudo must be installed during create()")


def test_create_fails_gracefully_when_proot_distro_missing() -> None:
    messages: list[str] = []
    result = create.create("test", "debian:13", log=messages.append)
    check(result is False, "create() should fail when proot-distro isn't installed")


TESTS = [
    test_dns_config_uses_cloudflare_matching_dextop,
    test_init_commands_match_dextop_container_initialization,
    test_init_commands_install_adduser_and_sudo,
    test_create_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
