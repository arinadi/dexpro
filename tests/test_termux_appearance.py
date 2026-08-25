"""app/native/termux_appearance.py: the real ~/.termux/font.ttf
customization mechanism, without a real Termux environment.

    python tests/test_termux_appearance.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import termux_appearance


def test_set_font_rejects_a_nonexistent_source() -> None:
    messages: list[str] = []
    result = termux_appearance.set_font("/definitely/not/a/real/font.ttf", log=messages.append)
    check(result is False, "must refuse a source path that doesn't exist")
    check(any("does not exist" in m for m in messages), f"got {messages!r}")


def test_set_font_copies_a_real_file() -> None:
    original = termux_appearance.FONT_PATH
    tmp = tempfile.mkdtemp(prefix="dexpro-termux-appearance-test-")
    termux_appearance.FONT_PATH = os.path.join(tmp, "termux-home", "font.ttf")

    source = os.path.join(tmp, "source.ttf")
    with open(source, "wb") as f:
        f.write(b"not a real font, just bytes to copy")

    try:
        messages: list[str] = []
        # termux-reload-settings doesn't exist on this dev machine, so
        # the overall result is False, but the copy itself must still
        # have happened — that's the part being tested here.
        termux_appearance.set_font(source, log=messages.append)
        check(os.path.exists(termux_appearance.FONT_PATH), "the font file must have been copied")
        with open(termux_appearance.FONT_PATH, "rb") as f:
            check(f.read() == b"not a real font, just bytes to copy", "copied content must match")
    finally:
        termux_appearance.FONT_PATH = original


def test_reload_settings_fails_gracefully_when_binary_missing() -> None:
    messages: list[str] = []
    result = termux_appearance.reload_settings(log=messages.append)
    check(result is False, "termux-reload-settings isn't real here — must report False, not raise")
    check(any("not found" in m for m in messages), f"got {messages!r}")


TESTS = [
    test_set_font_rejects_a_nonexistent_source,
    test_set_font_copies_a_real_file,
    test_reload_settings_fails_gracefully_when_binary_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
