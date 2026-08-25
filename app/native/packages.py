"""Native Termux package management — the Termux-side equivalent of
box/packages.py, operating directly on `pkg`/`apt` instead of a
proot-distro container. Enables community repos (tur-repo and others)
so the Termux Store screen has more than the bare main repo to search,
matching XLabs' Store screen feature set (search/install/uninstall,
repo enable) applied to the Termux side rather than a single container.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

from ..box.packages import SAFE_TERM, is_safe_term

Log = Callable[[str], None]

CURATED_PACKAGES: tuple[str, ...] = (
    "git",
    "python",
    "nodejs",
    "neovim",
    "vim",
    "curl",
    "wget",
    "htop",
    "tmux",
    "jq",
    "openssh",
    "termux-api",
)

# Termux's own official repos: each is enabled by installing a small
# meta-package that drops a sources.list.d entry — the same mechanism
# install.py already uses for x11-repo/tur-repo. name -> description.
REPOS: tuple[tuple[str, str], ...] = (
    ("x11-repo", "GUI/X11 packages (termux-x11-nightly, virglrenderer-android, xfce4, ...)"),
    ("tur-repo", "Termux User Repository — community-maintained packages"),
    ("game-repo", "Game-related packages"),
    ("science-repo", "Scientific computing packages"),
    ("root-repo", "Packages that assume/support a rooted device"),
    ("unstable-repo", "Bleeding-edge package versions"),
)


def enabled_repos() -> set[str]:
    """Which of REPOS are currently enabled. dpkg-query is a cheap,
    reliable check without hand-parsing sources.list.d: pkg installing
    e.g. tur-repo installs a real, queryable dpkg package by that name."""
    return {name for name, _description in REPOS if _dpkg_installed(name)}


def _dpkg_installed(package: str) -> bool:
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", package],
            capture_output=True,
            timeout=10,
            text=True,
        )
        return "install ok installed" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def enable_repo(name: str, log: Log | None = None) -> bool:
    if name not in {repo for repo, _description in REPOS}:
        if log:
            log(f"unknown repo: {name!r}")
        return False
    if not _run(["pkg", "install", "-y", name], timeout=120, log=log):
        return False
    return _run(["pkg", "update", "-y"], timeout=120, log=log)


def search(term: str, log: Log | None = None) -> list[str]:
    # apt-cache, not `pkg search`: `pkg` is Termux's own wrapper and
    # prints a "Checking availability of current mirror" preamble to
    # stdout before results, which the caller can't tell apart from a
    # real match — it was landing as a bogus row in the results table.
    # `pkg search` also formats each hit as a multi-line block
    # ("name/repo,now version arch" then an indented description line),
    # which breaks the one-line-per-package assumption the table/select
    # logic depends on (selecting the description line and extracting
    # its first word installs garbage, not the package). apt-cache
    # search --names-only gives one "name - description" line per
    # match, same format box/packages.py's container-side search()
    # already relies on.
    if not is_safe_term(term):
        if log:
            log(f"rejected unsafe search term: {term!r}")
        return []
    try:
        result = subprocess.run(
            ["apt-cache", "search", "--names-only", term],
            capture_output=True,
            timeout=30,
            text=True,
            check=True,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: search failed: {exc}")
        return []


def install(names: list[str], log: Log | None = None) -> bool:
    unsafe = [p for p in names if not is_safe_term(p)]
    if unsafe:
        if log:
            log(f"rejected unsafe package name(s): {unsafe!r}")
        return False
    return _run(["pkg", "install", "-y", *names], timeout=300, log=log)


def ensure_binary(
    binary: str,
    package: str | None = None,
    log: Log | None = None,
    attempted: set[str] | None = None,
) -> bool:
    """True if `binary` is on PATH, installing `package` (defaults to
    `binary`'s own name) via `install()` first if it's missing. Always
    re-checks with shutil.which afterward — never assumes install()
    succeeding means the binary actually landed on PATH.

    2026-08-26: extracted from a one-off version written for GPU Bench
    (which reported "no candidate produced a score" with zero explanation
    — the real cause was glmark2 never being installed anywhere) so every
    other native-side feature with the same "silently degrades if some
    binary is missing" shape can call the same, single, tested path
    instead of copy-pasting it.

    `attempted` (optional — a caller doing several of these in one run,
    e.g. gpu.bench() across its candidate presets, passes the same set
    through all of them) stops a genuinely failing install from being
    retried, and re-timed-out, once per caller.
    """
    if shutil.which(binary) is not None:
        return True
    if attempted is not None:
        if binary in attempted:
            return False
        attempted.add(binary)
    if not install([package or binary], log=log):
        return False
    if shutil.which(binary) is not None:
        return True
    # install() reported success (pkg/apt exited 0), but the binary still
    # isn't on PATH — apt considers "cannot locate this package name" a
    # non-fatal warning in some cases rather than a failing exit code, so
    # a bare exit-code check alone can't be trusted here (confirmed by a
    # real report: "pkg install langsung done tanpa log install" — no
    # visible reason the binary was still missing after a "successful"
    # run). Log the contradiction explicitly instead of a silent False.
    if log:
        log(
            f"{package or binary} install reported success, but {binary} still "
            f"isn't on PATH — check the output above for 'Unable to locate "
            f"package': the package name may not exist under this name in "
            f"Termux's repos, or it installs a different binary than expected"
        )
    return False


def uninstall(names: list[str], log: Log | None = None) -> bool:
    unsafe = [p for p in names if not is_safe_term(p)]
    if unsafe:
        if log:
            log(f"rejected unsafe package name(s): {unsafe!r}")
        return False
    return _run(["pkg", "uninstall", "-y", *names], timeout=120, log=log)


def _run(command: list[str], timeout: float, log: Log | None) -> bool:
    # Reported live as an empty log window on Enable/Install/Uninstall:
    # this previously only ever called log() on failure, so a successful
    # run showed nothing at all — no announced command, no confirmation.
    if log:
        log(f"$ {' '.join(command)}")
    try:
        result = subprocess.run(
            command, capture_output=True, timeout=timeout, check=True, text=True
        )
        if log:
            # 2026-08-26: a real device report of "pkg install just says
            # done, no install log" turned up that a *successful* (exit 0)
            # run discarded its own output entirely — apt/pkg's actual
            # per-package output (what it resolved, what it skipped, a
            # non-fatal "Unable to locate package" that doesn't always
            # fail the whole exit code) was never shown, only "done".
            # Surfacing it is what actually lets a report like "I suspect
            # glmark2 doesn't exist in Termux" be confirmed or ruled out
            # from the log itself, not by guessing.
            output = (result.stdout + result.stderr).strip()
            if output:
                for line in output.splitlines():
                    log(f"    {line}")
            log("done")
        return True
    except subprocess.CalledProcessError as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc.stderr}")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"error: {' '.join(command)} failed: {exc}")
        return False


__all__ = [
    "CURATED_PACKAGES",
    "REPOS",
    "SAFE_TERM",
    "enable_repo",
    "enabled_repos",
    "ensure_binary",
    "install",
    "is_safe_term",
    "search",
    "uninstall",
]
