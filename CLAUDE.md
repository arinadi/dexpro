# CLAUDE.md — Agent Guide for dexpro

This file is for whoever (human or agent) works on this codebase next. It exists because this project was built entirely without access to Termux or an Android device — every verification technique below was worked out from scratch this session, several after a technique that looked reasonable turned out to be wrong on first real test. Read this before assuming a "should work" claim is a "does work" claim.

## Read first

- `PRD.md` — architecture and rationale, plus a §10 Addendum with corrections found after the initial design.
- `build-task-phase1.md` through `build-task-phase5.md` — the actual build plan **and**, at the bottom of each, a "Verified on-device" (or "on-network") section listing exactly what was confirmed by running real code against a real `proot-distro`/Debian mirror/Linux container, versus what's still only logic-tested or entirely unverified. Treat these sections as living, authoritative status — update them, don't let them go stale.

## The core problem: no Termux, no Android device

Development happens on a Windows machine. `proot-distro`, `termux-x11`, Android's `am` command, and real GPU hardware don't exist here. Three tiers of verification were built to compensate — use the right one, and never claim a higher tier of confidence than what you actually ran.

### Tier 1 — local venv (fastest, most limited)

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install textual ruff   # Windows; drop Scripts/ on POSIX
./.venv/Scripts/python.exe tests/run_tests.py
./.venv/Scripts/python.exe -m ruff check .
```

This genuinely exercises:
- All pure logic (parsers, regex validators, command-string construction).
- Real Textual Pilot navigation (`app.run_test()` — a real Textual app, headless, no terminal needed).
- Anything that shells out to a tool that's ALSO present on this machine: `tar` (native home backup/restore — fully real, round-trip tested) and `curl` (mirror measurement — tested against the **live** Debian infrastructure, not mocked).

It does **not** exercise anything that needs `proot-distro`, `pkg`, `am`, `termux-x11`, or a real GPU. Those functions are written to fail gracefully (return `False`/`None`, log why) when the binary is missing — Tier 1 tests confirm that graceful-failure contract, not the real behavior.

One platform trap: `os.getuid()`/`os.symlink()` behave differently or don't exist on Windows. Tests touching those (`box/user.py`, `android/storage.py`) guard with `hasattr(os, "getuid")` or tolerate either outcome — see `tests/test_box_user.py` and `tests/test_android_storage.py` for the pattern. Don't remove those guards to "simplify" a test; they're load-bearing.

### Tier 2 — Podman dev container (real Termux packages, real proot-distro)

`docker/dev/Dockerfile` builds on `termux/termux-docker` and installs the real Termux packages (`pkg install`) this project needs. It is the closest thing to a real device available. **Every Doctor/box/export bug this session actually found was caught here, not in Tier 1.**

```bash
bash test-tui.sh          # builds the image, runs the full suite inside it
```

Or manually, for iterating on a specific check:

```bash
export MSYS_NO_PATHCONV=1   # see gotcha below — required on Git Bash/Windows
podman build --format docker -t dexpro-dev -f docker/dev/Dockerfile docker/dev
PROJECT_DIR="$(cygpath -w "$(pwd)")"   # Windows path translation for the volume mount
podman run --rm -v "${PROJECT_DIR}:/data/data/com.termux/files/home/dexpro" \
    dexpro-dev //data/data/com.termux/files/usr/bin/bash -c "
        cd /data/data/com.termux/files/home/dexpro
        pip install textual --quiet --break-system-packages
        python3 tests/run_tests.py
    "
```

For anything involving `proot-distro` itself (box create/user/export/backup), install it inside a running container and drive the real Python modules directly — this is how every Phase 2–5 bug in this codebase was actually found:

```bash
podman run --rm -d --name dexpro-test -v "${PROJECT_DIR}:/data/data/com.termux/files/home/dexpro" \
    dexpro-dev //data/data/com.termux/files/usr/bin/bash -c "sleep 900"
podman exec --user 1000:1000 dexpro-test //data/data/com.termux/files/usr/bin/bash -c "
    export HOME=/data/data/com.termux/files/home
    mkdir -p \$HOME && cd \$HOME
    pkg install -y proot-distro
    cd /data/data/com.termux/files/home/dexpro
    python3 -c \"
import sys; sys.path.insert(0, '.')
from app.box import create, user
create.create('test', 'debian:13', log=print)
user.add_user('test', 'dev', sudo=True, log=print)
\"
"
podman rm -f dexpro-test   # always clean up — containers left running accumulate
```

**Podman/Termux-image gotchas found this session — don't rediscover these the hard way:**

- **`SHELL` in the Dockerfile needs `podman build --format docker`.** Podman defaults to OCI image format, which silently *ignores* the `SHELL` directive (a warning, not an error — easy to miss). Without it, `RUN` falls back to `/bin/sh`, which doesn't exist in this image (Termux has no FHS `/bin` at all — confirmed XLabs' own, structurally identical Dockerfile hits the exact same failure on this Podman version). Always `--format docker`.
- **`x11-repo` must be installed and re-`pkg update`d before anything that lives in it** (`xfce4`, `termux-x11-nightly`, `virglrenderer`, ...). Installing them in the same `pkg install` batch as `x11-repo` itself fails with "Unable to locate package" — apt doesn't know about the new repo yet.
- **Git Bash/MSYS mangles POSIX-looking paths in command-line arguments** before they reach `podman.exe` (`/bin/sh` silently becomes `C:/Program Files/Git/usr/bin/sh`). Set `export MSYS_NO_PATHCONV=1` before any `podman run`/`exec` command that passes a container-side absolute path as an argument.
- **`podman exec` as root breaks PulseAudio and HOME-dependent behavior.** Always `--user 1000:1000` (or whatever UID you're simulating) and export `HOME` explicitly inside the exec'd command.
- **`proot-distro --version` doesn't exist** — it's an unrecognized command that dumps a help screen, which happens to end with a `PRoot-Distro version 'X.Y.Z'` footer. `app/box/manager.py::version()` parses that footer via `proot-distro help`; don't "fix" it back to `--version`.
- **`proot-distro install` pre-populates `/etc/passwd` with Android's `aid_*` UID table** (e.g. `aid_system:1000:1000`). Creating a user at a UID that collides with one of those is a real, reproducible failure — `app/box/user.py` handles it (detect the placeholder, rewrite `/etc/passwd`/`/etc/shadow` directly rather than via `usermod`, which **cannot** rename an account under proot: the very process running the rename is itself, at the kernel level, using that UID, since proot has no real UID namespaces — confirmed via `usermod: user X is currently used by process 1`, not a flake).
- **`pactl info` autospawns a PulseAudio daemon as a side effect of checking whether one is running.** `app/native/audio.py::is_running()` sets `PULSE_AUTOSPAWN=0` to make it a genuine read-only probe — don't remove that env var thinking it's unnecessary.
- **The official `debian:13` Docker Hub image (what `proot-distro install debian:13` actually pulls) has no `adduser`/`sudo` installed.** `box/create.py`'s init chain installs both explicitly; without it, every fresh container breaks user creation.
- **`curl -w "%{speed_download}"` prints `0` even when the whole request failed** (DNS resolution error, exit code 6). Check `returncode` before trusting the output — `box/mirror.py::measure_speed()` does this now; a version that doesn't will silently report an unreachable mirror as "measured, 0 speed" instead of "couldn't measure."
- **WSLg's real X11 socket on a Podman machine is at `/mnt/wslg/.X11-unix/X0`, not `/tmp/.X11-unix`** — a minimal Podman-machine VM doesn't get the same auto-bind-mount a full WSL2 distro does. Verify with `podman machine ssh <name> "ls /mnt/wslg/.X11-unix /tmp/.X11-unix"` before assuming either path in `docker-compose.yml`.

### Tier 3 — real device (unverified in this codebase so far)

Nothing here has been tried. The specific open questions are enumerated in each `build-task-phase*.md`'s spike table / "Verified on-device" section — most notably, **whether a native XFCE session actually renders on a real phone is still unconfirmed**; a bounded attempt to validate an analogous render via WSLg passthrough hit a real, unresolved `Cannot open display: .` error and was deliberately not chased further (see `build-task-phase1.md`). Don't write documentation or commit messages implying this is confirmed — it isn't.

## Test harness conventions

`tests/` uses a small custom harness (`support.py`'s `check()`/`run()`), **not pytest** — mirrors XLabs' own approach, which the project explicitly modeled testing on. Each `test_*.py` module exports a `TESTS` list and has a `if __name__ == "__main__"` block so it can run standalone while iterating:

```bash
python tests/test_box_export.py     # just this module
python tests/run_tests.py           # everything, in the order run_tests.py wires up
```

New test module → add its `TESTS` import to `tests/run_tests.py` and fold it into `ALL_TESTS`, or it silently never runs.

## Code conventions established this session

- **Every function that shells out or touches the filesystem returns `bool`/`None`/`Optional[...]` and logs via an optional `log: Callable[[str], None]` — never raises for an expected failure** (missing binary, unreachable network, permission denied). Tests exercise this by asserting "returns a definite bool/None, doesn't crash," not by asserting a specific outcome that varies by environment (see `test_wakelock.py`, `test_box_manager.py`'s "fails gracefully" tests for the pattern).
- **Docstrings say what's ported vs. adapted vs. genuinely new**, and cite the source project (XLabs/dextop) and the specific reason for any deviation. This isn't decoration — `build-task-phase2.md`'s "Critical correction" and `user.py`'s docstring are what saved a second implementer from re-discovering the `aid_*`/`usermod` problem from scratch.
- **When a design assumption turns out wrong after a real test, fix the code, fix the test, and write down what was wrong and why in both the module docstring and the relevant `build-task-phaseN.md`'s "Verified on-device" section.** Silently patching without recording the finding is how the same bug gets reintroduced later.
- Line length 100, `ruff.toml`'s `E`/`F`/`I`/`UP`/`B` rule sets. Run `ruff check .` before considering anything done — several real bugs in this session were only line-length violations away from being caught earlier by lint alone (import ordering, unused imports).

## What "done" means here

A phase being "implemented" is not the same as being "verified." Before claiming either in a commit message or to whoever you're reporting to: state plainly which tier (1/2/3) actually ran, and if something is Tier-3-only (unverified), say so — don't imply Tier 2 coverage proves something Tier 2 structurally cannot prove (anything needing `am`, real GPU hardware, or an actual X11 render target).
