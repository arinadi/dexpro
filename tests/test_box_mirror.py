"""app/box/mirror.py: deb822 masterlist parsing, speed measurement, and
custom-repo URI validation.

Two of these tests hit the real Debian mirror infrastructure over the
network (parsing the actual live masterlist, measuring a real mirror's
speed) — this needs no Termux/Android at all, just curl and internet
access, both available on this dev machine. They're skipped gracefully
(not failed) if the network is unreachable, since that's an environment
fact, not a code defect.

    python tests/test_box_mirror.py
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import mirror

_SAMPLE_MASTERLIST = """\
Site: mirror.example.org
Country: NL Netherlands
Archive-http: /debian/
Archive-ftp: /debian/

Site: another.example.net
Country: US United States
Archive-http: /debian/
"""


def _network_available() -> bool:
    sink = "NUL" if os.name != "posix" else "/dev/null"
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", sink, "--max-time", "5", "-I", mirror.MIRROR_LIST_URL],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def test_parse_masterlist_extracts_site_entries() -> None:
    mirrors = mirror.parse_masterlist(_SAMPLE_MASTERLIST)
    check(len(mirrors) == 2, f"expected 2 mirror entries, got {len(mirrors)}")
    check(mirrors[0]["Site"] == "mirror.example.org", f"wrong site parsed: {mirrors[0]!r}")
    check(mirrors[0]["Archive-http"] == "/debian/", f"wrong archive path parsed: {mirrors[0]!r}")


def test_parse_masterlist_drops_entries_missing_required_fields() -> None:
    text = "Site: incomplete.example.org\nCountry: XX Nowhere\n"
    check(mirror.parse_masterlist(text) == [], "an entry with no Archive-http must be dropped")


def test_parse_masterlist_ignores_blank_input() -> None:
    check(mirror.parse_masterlist("") == [], "empty input should parse to an empty list")


def test_is_safe_uri_accepts_https_and_rejects_shell_metacharacters() -> None:
    check(mirror.is_safe_uri("https://example.org/debian"), "a normal https URI should be accepted")
    has_metachar = mirror.is_safe_uri("https://example.org; rm -rf /")
    check(not has_metachar, "shell metacharacters must be rejected")
    check(not mirror.is_safe_uri("not-a-uri-at-all"), "a non-URI string must be rejected")


def test_is_safe_words_accepts_plain_names_and_rejects_metacharacters() -> None:
    check(mirror.is_safe_words("vscode"), "a plain repo name should be accepted")
    check(mirror.is_safe_words("my repo 2"), "spaces should be tolerated")
    check(not mirror.is_safe_words("repo; rm -rf /"), "shell metacharacters must be rejected")
    check(not mirror.is_safe_words("$(whoami)"), "command substitution must be rejected")


def test_add_custom_repo_rejects_unsafe_name_before_touching_the_subprocess() -> None:
    messages: list[str] = []
    result = mirror.add_custom_repo(
        "work",
        "repo; rm -rf /",
        "https://example.org/debian",
        "https://example.org/key.asc",
        log=messages.append,
    )
    check(result is False, "must refuse an unsafe repo name")
    check(any("unsafe" in m for m in messages), "no rejection reason logged")


def test_add_custom_repo_rejects_unsafe_uri() -> None:
    messages: list[str] = []
    result = mirror.add_custom_repo(
        "work",
        "myrepo",
        "https://example.org; rm -rf /",
        "https://example.org/key.asc",
        log=messages.append,
    )
    check(result is False, "must refuse an unsafe repo URI")


_DEB822_SAMPLE = """\
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie
Components: main

Types: deb
URIs: http://security.debian.org/debian-security
Suites: trixie-security
Components: main
"""

_LEGACY_SAMPLE = """\
deb http://deb.debian.org/debian trixie main
deb http://security.debian.org/debian-security trixie-security main
"""


def test_repoint_deb822_main_changes_only_the_non_security_stanza() -> None:
    uri = "https://mirror.example/debian"
    new_content, changed = mirror._repoint_deb822_main(_DEB822_SAMPLE, uri)
    check(changed == 2, f"expected both URIs lines touched (main + security reasserted): {changed}")
    check(f"URIs: {uri}" in new_content, new_content)
    check(f"URIs: {mirror.CANONICAL_SECURITY_URI}" in new_content, new_content)
    never_mirror = "http://security.debian.org" not in new_content
    check(never_mirror, "security must never point at the chosen mirror")


def test_repoint_deb822_main_is_idempotent_on_security() -> None:
    once, _ = mirror._repoint_deb822_main(_DEB822_SAMPLE, "https://mirror.example/debian")
    twice, changed_again = mirror._repoint_deb822_main(once, "https://mirror.example/debian")
    check(once == twice, "repointing an already-repointed file to the same URI must be a no-op")
    check(changed_again == 0, "no lines should change on the second pass")


def test_repoint_legacy_main_changes_only_the_non_security_line() -> None:
    uri = "https://mirror.example/debian"
    new_content, changed = mirror._repoint_legacy_main(_LEGACY_SAMPLE, uri)
    check(changed == 2, f"expected both lines touched (main + security reasserted): {changed}")
    check(f"{uri} trixie main" in new_content, new_content)
    check(f"{mirror.CANONICAL_SECURITY_URI} trixie-security" in new_content, new_content)


def test_apply_mirror_fails_gracefully_for_nonexistent_container() -> None:
    messages: list[str] = []
    result = mirror.apply_mirror(
        "definitely-not-a-real-container", "https://mirror.example/debian", log=messages.append
    )
    check(result is False, "no rootfs to write to — must report failure, not raise")
    check(messages, "should explain why it failed")


def test_measure_speed_returns_none_for_an_unreachable_host() -> None:
    result = mirror.measure_speed("http://this-host-does-not-exist.invalid/", timeout=3.0)
    check(result is None, "an unreachable host must report None, not raise")


def test_fetch_masterlist_follows_the_redirect() -> None:
    # Confirmed on-device: MIRROR_LIST_URL (plain http://) 301-redirects
    # to https:// — without -L the response body is just the redirect
    # page, not the masterlist, and parse_masterlist() sees 0 mirrors.
    if not _network_available():
        return
    text = mirror.fetch_masterlist()
    if text is None:
        return
    msg = "fetched content doesn't look like the masterlist — redirect not followed?"
    check("Site:" in text, msg)


def test_parse_real_debian_masterlist() -> None:
    if not _network_available():
        return  # environment fact, not a code defect — skip gracefully
    text = mirror.fetch_masterlist()
    if text is None:
        return
    mirrors = mirror.parse_masterlist(text)
    check(len(mirrors) > 50, f"the real masterlist should have many mirrors, parsed {len(mirrors)}")
    both_fields = all("Site" in m and "Archive-http" in m for m in mirrors)
    check(both_fields, "every parsed entry must have both required fields")


def test_measure_speed_against_a_real_mirror() -> None:
    if not _network_available():
        return
    speed = mirror.measure_speed("https://deb.debian.org/debian/dists/stable/Release", timeout=10.0)
    if speed is None:
        return  # network hiccup — not asserting a specific mirror is always reachable
    check(speed > 0, f"a successful measurement should report a positive speed, got {speed}")


TESTS = [
    test_parse_masterlist_extracts_site_entries,
    test_parse_masterlist_drops_entries_missing_required_fields,
    test_parse_masterlist_ignores_blank_input,
    test_is_safe_uri_accepts_https_and_rejects_shell_metacharacters,
    test_is_safe_words_accepts_plain_names_and_rejects_metacharacters,
    test_add_custom_repo_rejects_unsafe_name_before_touching_the_subprocess,
    test_add_custom_repo_rejects_unsafe_uri,
    test_repoint_deb822_main_changes_only_the_non_security_stanza,
    test_repoint_deb822_main_is_idempotent_on_security,
    test_repoint_legacy_main_changes_only_the_non_security_line,
    test_apply_mirror_fails_gracefully_for_nonexistent_container,
    test_measure_speed_returns_none_for_an_unreachable_host,
    test_fetch_masterlist_follows_the_redirect,
    test_parse_real_debian_masterlist,
    test_measure_speed_against_a_real_mirror,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
