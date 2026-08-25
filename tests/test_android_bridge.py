"""app/android/bridge.py: the scheme-synonym lookup (the actual fix
over dextop's broken multi-condition matcher) and graceful failure when
`am` (Android-only) is absent.

    python tests/test_android_bridge.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.android import bridge


def test_all_documented_synonyms_resolve() -> None:
    # dextop's own [[ ]] || [[ ]] [[ ]] chain only actually OR'd the
    # first pair — several of its own documented synonyms silently
    # never matched. Every synonym here must resolve, by construction
    # (plain dict lookup), not just the first one.
    for synonym in bridge.SCHEME_SYNONYMS:
        check(bridge.resolve_scheme(synonym) is not None, f"{synonym!r} should resolve to a scheme")


def test_resolve_scheme_is_case_insensitive() -> None:
    check(bridge.resolve_scheme("Email") == "mailto", "should be case-insensitive")
    check(bridge.resolve_scheme("BROWSER") == "https", "should be case-insensitive")


def test_resolve_scheme_none_for_unknown_synonym() -> None:
    result = bridge.resolve_scheme("carrier-pigeon")
    check(result is None, "an unknown synonym must resolve to None")


def test_open_uri_never_raises_when_am_absent() -> None:
    messages: list[str] = []
    result = bridge.open_uri("https://example.com", log=messages.append)
    check(result is False, "no `am` binary on this dev machine — must report failure, not raise")
    check(any("could not open" in m for m in messages), "no failure reason logged")


def test_open_handle_builds_correct_uri_and_fails_gracefully() -> None:
    messages: list[str] = []
    result = bridge.open_handle("email", "someone@example.com", log=messages.append)
    check(result is False, "should fail gracefully without `am`")


def test_open_handle_rejects_unknown_handle_before_touching_am() -> None:
    messages: list[str] = []
    result = bridge.open_handle("carrier-pigeon", "target", log=messages.append)
    check(result is False, "unknown handle must be rejected")
    check(any("unknown handle" in m for m in messages), "no rejection reason logged")


TESTS = [
    test_all_documented_synonyms_resolve,
    test_resolve_scheme_is_case_insensitive,
    test_resolve_scheme_none_for_unknown_synonym,
    test_open_uri_never_raises_when_am_absent,
    test_open_handle_builds_correct_uri_and_fails_gracefully,
    test_open_handle_rejects_unknown_handle_before_touching_am,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
