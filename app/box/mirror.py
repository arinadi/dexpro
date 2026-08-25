"""Debian mirror measurement and custom repo management — ported from
XLabs' packages.py mirror/repo logic (build-task-phase5.md Task 4),
parameterized per-container.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

from . import manager, packages

Log = Callable[[str], None]

MIRROR_LIST_URL = "http://mirror-master.debian.org/status/Mirrors.masterlist"
CANONICAL_SECURITY_URI = "https://security.debian.org/debian-security"

SOURCES_DEB822 = "/etc/apt/sources.list.d/debian.sources"
SOURCES_LEGACY = "/etc/apt/sources.list"

# Shell-injection defense for custom repo fields — allow-list by
# rejection, same discipline as box/packages.py's SAFE_TERM.
SAFE_URI = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")
SAFE_WORDS = re.compile(r"^[A-Za-z0-9 ._-]+$")


def parse_masterlist(text: str) -> list[dict[str, str]]:
    """Parses the deb822-format Mirrors.masterlist into a list of
    {"Site": ..., "Archive-http": ..., ...} entries — the deb822
    masterlist, not the HTML mirror page (XLabs' exact source choice).
    Pure function — takes text rather than fetching it, testable
    offline and against a real fetch alike."""
    mirrors: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            if current:
                mirrors.append(current)
                current = {}
            continue
        if line.startswith(" ") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        current[key.strip()] = value.strip()
    if current:
        mirrors.append(current)
    return [m for m in mirrors if "Site" in m and "Archive-http" in m]


def fetch_masterlist(timeout: float = 15.0) -> str | None:
    """Fetches the real masterlist. Confirmed on-device: MIRROR_LIST_URL
    (plain http://) 301-redirects to https:// — `-L` is required or the
    response body is just the redirect page, not the masterlist (this
    was missing initially and made parse_masterlist() see 0 mirrors
    against the real URL)."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), MIRROR_LIST_URL],
            capture_output=True,
            timeout=timeout + 5,
            text=True,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def measure_speed(url: str, timeout: float = 10.0) -> float | None:
    """`curl -w "%{speed_download}"` — XLabs' exact measurement
    approach: a real download-speed probe against a real file, not
    ICMP ping.

    Confirmed on-device: curl still prints `speed_download=0` even when
    it fails outright (e.g. exit code 6, DNS resolution failure) — the
    original version of this function parsed that "0" as a valid float
    instead of None, silently treating a completely unreachable host as
    "measured, zero speed" rather than "couldn't measure at all". Now
    checks the exit code first.
    """
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-o",
                "/dev/null" if _posix() else "NUL",
                "-w",
                "%{speed_download}",
                "--max-time",
                str(timeout),
                url,
            ],
            capture_output=True,
            timeout=timeout + 5,
            text=True,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return None


def _posix() -> bool:
    import os

    return os.name == "posix"


def pick_fastest(
    mirrors: list[dict[str, str]], suite: str = "trixie", limit: int = 5
) -> dict[str, str] | None:
    """Measures up to `limit` candidate mirrors and returns the
    fastest. Capped so this doesn't take forever against a long
    masterlist — not exhaustive, best-effort."""
    best: tuple[dict[str, str], float] | None = None
    for candidate in mirrors[:limit]:
        base = candidate.get("Archive-http", "").rstrip("/")
        if not base:
            continue
        speed = measure_speed(f"{base}/dists/{suite}/Release")
        if speed is None:
            continue
        if best is None or speed > best[1]:
            best = (candidate, speed)
    return best[0] if best else None


def is_safe_uri(uri: str) -> bool:
    return bool(SAFE_URI.match(uri))


def is_safe_words(text: str) -> bool:
    return bool(SAFE_WORDS.match(text))


def _sources_file(container: str) -> str | None:
    """Whichever sources file this container actually uses — modern
    Debian images (debian:13/trixie) ship deb822, older ones legacy."""
    rootfs = manager.container_rootfs_path(container)
    if rootfs is None:
        return None
    for path in (SOURCES_DEB822, SOURCES_LEGACY):
        if os.path.exists(os.path.join(rootfs, path.lstrip("/"))):
            return path
    return None


def _is_security_suite(suite: str) -> bool:
    return suite == "security" or suite.endswith("-security")


def _parse_deb822_stanzas(content: str) -> list[list[str]]:
    stanzas: list[list[str]] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.strip() == "":
            if current:
                stanzas.append(current)
                current = []
        else:
            current.append(line)
    if current:
        stanzas.append(current)
    return stanzas


def _deb822_stanza_is_security(stanza: list[str]) -> bool:
    for line in stanza:
        stripped = line.strip()
        if stripped.startswith("Suites:"):
            return any(_is_security_suite(s) for s in stripped.split(":", 1)[1].split())
    return False


def _repoint_deb822_main(content: str, uri: str) -> tuple[str, int]:
    stanzas = _parse_deb822_stanzas(content)
    changed = 0
    for stanza in stanzas:
        is_security = _deb822_stanza_is_security(stanza)
        for i, line in enumerate(stanza):
            if not line.strip().startswith("URIs:"):
                continue
            new_value = CANONICAL_SECURITY_URI if is_security else uri
            replacement = f"URIs: {new_value}"
            if line != replacement:
                stanza[i] = replacement
                changed += 1
    return "\n\n".join("\n".join(s) for s in stanzas) + "\n", changed


def _legacy_line_is_security(stripped: str) -> bool:
    parts = stripped.split()
    return len(parts) >= 3 and _is_security_suite(parts[2])


def _repoint_legacy_main(content: str, uri: str) -> tuple[str, int]:
    lines = content.splitlines()
    changed = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith(("deb ", "deb-src ")) and "://" in stripped):
            continue
        parts = stripped.split()
        new_uri = CANONICAL_SECURITY_URI if _legacy_line_is_security(stripped) else uri
        if parts[1] != new_uri:
            parts[1] = new_uri
            lines[i] = " ".join(parts)
            changed += 1
    return "\n".join(lines) + "\n", changed


def apply_mirror(container: str, uri: str, log: Log | None = None) -> bool:
    """Points the container's main Debian archive at `uri`, rewritten
    directly on the host-side rootfs (no container login needed, and it
    works even if apt inside the container is currently broken). The
    security stanza is always forced to CANONICAL_SECURITY_URI — never to
    the chosen mirror, since ordinary mirrors aren't required to carry
    debian-security. Rolls back to the original file if `apt-get update`
    then fails against the new mirror, mirroring XLabs' set_mirror.
    """
    rootfs = manager.container_rootfs_path(container)
    rel_path = _sources_file(container)
    if rootfs is None or rel_path is None:
        if log:
            log(f"error: no Debian sources file found for '{container}'")
        return False

    target = os.path.join(rootfs, rel_path.lstrip("/"))
    try:
        with open(target, encoding="utf-8") as f:
            original = f.read()
    except OSError as exc:
        if log:
            log(f"error: could not read {rel_path}: {exc}")
        return False

    repoint = _repoint_deb822_main if rel_path == SOURCES_DEB822 else _repoint_legacy_main
    new_content, changed = repoint(original, uri)
    if not changed:
        if log:
            log(f"error: no archive line found in {rel_path}")
        return False

    def _write(content: str) -> bool:
        try:
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            return True
        except OSError as exc:
            if log:
                log(f"error: could not write {rel_path}: {exc}")
            return False

    if not _write(new_content):
        return False
    if log:
        log(f"{rel_path} now points at {uri} ({changed} line(s) changed)")

    if packages.update_lists(container, log=log):
        return True

    if log:
        log("apt could not use that mirror — putting the old sources back")
    _write(original)
    packages.update_lists(container, log=log)
    return False


def add_custom_repo(
    container: str, name: str, uri: str, key_url: str, log: Log | None = None
) -> bool:
    """Requires an explicit signing key URL — never trust a third-party
    repo via Debian's own keyring, matching XLabs' rationale exactly."""
    if not is_safe_words(name):
        if log:
            log(f"rejected unsafe repo name: {name!r}")
        return False
    if not (is_safe_uri(uri) and is_safe_uri(key_url)):
        if log:
            log("rejected unsafe repo/key URI")
        return False
    keyring_path = f"/etc/apt/keyrings/dexpro-{name}.asc"
    script = (
        f"curl -fsSL {key_url} -o {keyring_path} && "
        f"echo 'deb [signed-by={keyring_path}] {uri} stable main' "
        f"> /etc/apt/sources.list.d/dexpro-{name}.list"
    )
    if log:
        log(f"adding repo {name!r} ({uri}) to '{container}'")
    full = manager.login_command(container, ["sh", "-c", script])
    try:
        subprocess.run(full, capture_output=True, timeout=30, check=True)
        if log:
            log("done")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: could not add repo {name!r}: {exc}")
        return False
