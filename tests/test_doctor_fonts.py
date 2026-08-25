"""app/doctor/fonts.py: the surgical INI-section patch — genuinely
testable locally, no Termux needed (pure Python file manipulation).

    python tests/test_doctor_fonts.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.doctor import fonts


def test_patch_terminal_font_creates_file_when_absent() -> None:
    tmp_dir = tempfile.mkdtemp(prefix="dexpro-fonts-test-")
    path = os.path.join(tmp_dir, "nested", "terminalrc")
    try:
        result = fonts.patch_terminal_font(path=path)
        check(result, "should succeed even when the file/directory doesn't exist yet")
        check(os.path.exists(path), "file should have been created")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        check("FontName=Fira Code 11" in content, f"font key not set correctly: {content!r}")
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_patch_terminal_font_preserves_other_settings() -> None:
    # "Doesn't clobber other user settings" is the whole point of doing
    # a surgical patch instead of overwriting the file.
    tmp_dir = tempfile.mkdtemp(prefix="dexpro-fonts-test-")
    path = os.path.join(tmp_dir, "terminalrc")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("[Configuration]\nColorForeground=#ffffff\nMiscAlwaysShowTabs=TRUE\n")
        fonts.patch_terminal_font(path=path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        survives = "unrelated existing setting must survive the patch"
        check("ColorForeground=#ffffff" in content, survives)
        check("MiscAlwaysShowTabs=TRUE" in content, survives)
        check("FontName=Fira Code 11" in content, "font key must still be set")
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_patch_terminal_font_overwrites_a_stale_font_value() -> None:
    tmp_dir = tempfile.mkdtemp(prefix="dexpro-fonts-test-")
    path = os.path.join(tmp_dir, "terminalrc")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("[Configuration]\nFontName=Monospace 10\n")
        fonts.patch_terminal_font(path=path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        check("FontName=Fira Code 11" in content, "stale font value should be replaced")
        check("Monospace 10" not in content, "the old font value must not linger")
    finally:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)


TESTS = [
    test_patch_terminal_font_creates_file_when_absent,
    test_patch_terminal_font_preserves_other_settings,
    test_patch_terminal_font_overwrites_a_stale_font_value,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
