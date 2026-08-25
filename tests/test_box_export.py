"""app/box/export.py: wrapper script / .desktop content generation, the
dexpro-export marker (so delete never touches a file it didn't create),
and graceful behavior when proot-distro is absent.

    python tests/test_box_export.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import export


def _isolated_export_dirs(test):
    """Redirect export.py's host-side paths (normally ~/.local/bin etc.)
    into a temp dir for the duration of the test, so it never touches
    the real machine's actual export locations."""

    def wrapper():
        tmp = tempfile.mkdtemp(prefix="dexpro-export-test-")
        originals = (
            export.DEFAULT_BIN_EXPORT_DIR,
            export.DESKTOP_APPLICATIONS_DIR,
            export.ICONS_DIR,
        )
        export.DEFAULT_BIN_EXPORT_DIR = os.path.join(tmp, "bin")
        export.DESKTOP_APPLICATIONS_DIR = os.path.join(tmp, "applications")
        export.ICONS_DIR = os.path.join(tmp, "icons")
        try:
            test()
        finally:
            (
                export.DEFAULT_BIN_EXPORT_DIR,
                export.DESKTOP_APPLICATIONS_DIR,
                export.ICONS_DIR,
            ) = originals
            shutil.rmtree(tmp, ignore_errors=True)

    wrapper.__name__ = test.__name__
    return wrapper


def test_wrapper_script_execs_via_proot_distro_login() -> None:
    script = export.wrapper_script("work", "/usr/bin/nvim")
    check(script.startswith("#!/data/data/com.termux/files/usr/bin/bash\n"), "wrong shebang")
    login_line = "proot-distro login work --shared-tmp -- /usr/bin/nvim"
    check(login_line in script, "wrong login invocation")
    check('"$@"' in script, "must forward extra arguments to the wrapped binary")


@_isolated_export_dirs
def test_export_bin_writes_executable_marked_wrapper() -> None:
    target = export.export_bin("work", "/usr/bin/nvim")
    check(target is not None, "export_bin should succeed")
    check(os.path.exists(target), "wrapper file wasn't created")
    check(os.access(target, os.X_OK), "wrapper must be executable")
    marked = export.is_dexpro_bin_export(target)
    check(marked, "marker not detected on a file export.py itself wrote")


@_isolated_export_dirs
def test_delete_bin_export_refuses_files_it_did_not_create() -> None:
    os.makedirs(export.DEFAULT_BIN_EXPORT_DIR, exist_ok=True)
    foreign = os.path.join(export.DEFAULT_BIN_EXPORT_DIR, "not-mine")
    with open(foreign, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\necho hi\n")
    messages: list[str] = []
    result = export.delete_bin_export("not-mine", log=messages.append)
    check(result is False, "must refuse to delete a file it didn't export")
    check(os.path.exists(foreign), "the foreign file must survive the refused delete")
    check(any("refusing" in m for m in messages), "no refusal reason logged")


@_isolated_export_dirs
def test_delete_bin_export_removes_its_own_export() -> None:
    target = export.export_bin("work", "/usr/bin/nvim")
    deleted = export.delete_bin_export(os.path.basename(target))
    check(deleted, "delete of its own export should succeed")
    check(not os.path.exists(target), "wrapper should be gone after delete")


def test_patch_desktop_exec_prefixes_proot_distro_login() -> None:
    original = "[Desktop Entry]\nName=Neovim\nExec=nvim %F\nIcon=nvim\nType=Application\n"
    patched = export.patch_desktop_exec(original, "work")
    check(
        "Exec=proot-distro login work --shared-tmp -- nvim %F" in patched,
        f"Exec line not rewritten correctly: {patched!r}",
    )
    check("X-Dexpro-Container=work" in patched, "missing ownership marker key")
    check("Name=Neovim" in patched, "unrelated lines must survive untouched")


def test_patch_desktop_exec_tolerates_missing_exec_line() -> None:
    original = "[Desktop Entry]\nName=Weird\n"
    patched = export.patch_desktop_exec(original, "work")
    check("X-Dexpro-Container=work" in patched, "marker must be added even without an Exec= line")


def test_is_dexpro_app_export_checks_the_marker_and_container() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".desktop", delete=False, encoding="utf-8"
    ) as f:
        f.write("[Desktop Entry]\nExec=nvim\nX-Dexpro-Container=work\n")
        path = f.name
    try:
        check(export.is_dexpro_app_export(path), "should detect the marker")
        matches_own = export.is_dexpro_app_export(path, container="work")
        check(matches_own, "should match the right container")
        matches_other = export.is_dexpro_app_export(path, container="other")
        check(not matches_other, "must not match a different container")
    finally:
        os.remove(path)


def test_is_dexpro_app_export_false_for_unmarked_file() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".desktop", delete=False, encoding="utf-8"
    ) as f:
        f.write("[Desktop Entry]\nExec=some-other-app\n")
        path = f.name
    try:
        result = export.is_dexpro_app_export(path)
        check(not result, "a file dexpro didn't export must not be flagged as its own")
    finally:
        os.remove(path)


@_isolated_export_dirs
def test_list_exports_only_counts_marked_files() -> None:
    export.export_bin("work", "/usr/bin/nvim")
    os.makedirs(export.DEFAULT_BIN_EXPORT_DIR, exist_ok=True)
    with open(os.path.join(export.DEFAULT_BIN_EXPORT_DIR, "unrelated"), "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n")
    os.chmod(os.path.join(export.DEFAULT_BIN_EXPORT_DIR, "unrelated"), 0o755)

    result = export.list_exports()
    got = result["binaries"]
    check(got == ["nvim"], f"expected only the dexpro export, got {got!r}")


def test_desktop_find_script_joins_commands_with_a_separator() -> None:
    # Confirmed on-device: joining with a bare space produced ONE
    # malformed `find` command (the second `find ...` got parsed as
    # more arguments to the first), silently returning nothing against
    # a container that genuinely had a .desktop file. This test would
    # have caught it without needing a real proot-distro run.
    script = export.desktop_find_script()
    check(script.count("find ") == 2, f"expected two find invocations, got: {script!r}")
    has_separator = ";" in script
    check(has_separator, "find invocations must be joined with a separator, not a bare space")
    for directory in export._DESKTOP_SEARCH_DIRS:
        check(f"find {directory}" in script, f"missing a find invocation for {directory}")


def test_list_desktop_files_fails_gracefully_when_proot_distro_missing() -> None:
    result = export.list_desktop_files("work")
    check(result == [], f"expected an empty list when proot-distro is unavailable, got {result!r}")


def test_export_app_fails_gracefully_when_proot_distro_missing() -> None:
    messages: list[str] = []
    result = export.export_app("work", "/usr/share/applications/nvim.desktop", log=messages.append)
    check(result is None, "export_app() should fail when proot-distro isn't installed")


TESTS = [
    test_wrapper_script_execs_via_proot_distro_login,
    test_export_bin_writes_executable_marked_wrapper,
    test_delete_bin_export_refuses_files_it_did_not_create,
    test_delete_bin_export_removes_its_own_export,
    test_patch_desktop_exec_prefixes_proot_distro_login,
    test_patch_desktop_exec_tolerates_missing_exec_line,
    test_is_dexpro_app_export_checks_the_marker_and_container,
    test_is_dexpro_app_export_false_for_unmarked_file,
    test_list_exports_only_counts_marked_files,
    test_desktop_find_script_joins_commands_with_a_separator,
    test_list_desktop_files_fails_gracefully_when_proot_distro_missing,
    test_export_app_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
