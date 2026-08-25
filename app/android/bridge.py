"""Android app-bridging via generic scheme-based intent handoff —
concept ported from dextop-additions (build-task-phase5.md Task 2), NOT
its code.

Two confirmed bugs in the source are deliberately not carried forward:
1. dextop's `[[ ]] || [[ ]] [[ ]]` synonym-matching chains only actually
   OR the first pair — later conditions in the chain aren't properly
   joined, so several documented synonyms silently never match. This
   module uses a plain dict lookup instead, which has no such bug by
   construction.
2. The ~450 commented-out lines of Android intent constants are not
   ported as live code — reference material at most, not a shipped
   module.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

Log = Callable[[str], None]

# Synonym -> URI scheme. dextop's hardcoded per-activity-component list
# (chrome/gmail/terminal component names) is brittle against app
# updates/replacements — this scheme-based handoff to Android's own
# default-app resolution is the part of dextop's design worth keeping.
SCHEME_SYNONYMS: dict[str, str] = {
    "email": "mailto",
    "mail": "mailto",
    "browser": "https",
    "link": "https",
    "web": "https",
    "message": "sms",
    "text": "sms",
    "sms": "sms",
    "file": "file",
}


def resolve_scheme(synonym: str) -> str | None:
    return SCHEME_SYNONYMS.get(synonym.lower())


def open_uri(uri: str, log: Log | None = None) -> bool:
    cmd = ["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-d", uri]
    try:
        subprocess.run(cmd, capture_output=True, timeout=15, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: could not open {uri}: {exc}")
        return False


def open_handle(handle: str, target: str, log: Log | None = None) -> bool:
    """`handle` is a synonym like 'email'/'browser'/'sms'; `target` is
    the address/URL/number to open. Builds `<scheme>:<target>` and
    hands off to Android's own default-app resolution — no xdg-mime
    involved, matching dextop's own (sound) approach here."""
    scheme = resolve_scheme(handle)
    if scheme is None:
        if log:
            log(f"error: unknown handle {handle!r} — known: {sorted(SCHEME_SYNONYMS)}")
        return False
    return open_uri(f"{scheme}:{target}", log=log)
