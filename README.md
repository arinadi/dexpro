# dexpro

**Turn your DeX into a professional setup.**

A Python/Textual TUI for Android/Termux that runs a full desktop session **natively** (no `proot` in the GUI critical path) and provides a distrobox-style helper, `dexpro-box`, for isolated dev/CLI containers on top of `proot-distro`.

Built for Samsung DeX: proot's ptrace-based syscall interception scales badly with GUI syscall volume, which is fine on a phone-sized session but drags hard once you dock into a bigger DeX session. dexpro's fix is architectural — the desktop itself never runs inside proot at all; `proot-distro` containers are reserved for what they're actually good at, isolated toolchains, not hosting a whole GUI session.

See [`PRD.md`](PRD.md) for the full rationale, architecture, and research this project's design is grounded in (including corrections found after the initial design — read its §10 Addendum and each `build-task-phase*.md`'s own "Verified on-device" section for what's been confirmed vs. what's still open).

## Status

All five planned phases are implemented and covered by an automated test suite (133 tests as of Phase 5). What's **genuinely verified** — confirmed by actually running the code, not assumed — is documented per-phase in `build-task-phase1.md` through `build-task-phase5.md`. In short:

- **Verified for real**: native session lifecycle logic, `dexpro-box` container creation with host-UID-mapped users, app export, Doctor checks, native + container backup/restore, Debian mirror measurement — all confirmed against a real `proot-distro` CLI (in a Podman dev container) or real infrastructure (live Debian mirrors).
- **Not yet verified**: whether a native XFCE session actually *renders* on a real device (this project's core hypothesis) — see `build-task-phase1.md`'s spike table. Nothing that depends on Android's `am` command (storage permission triggers, app-scheme handoff) has been exercised either — no environment used during development has `am` at all.

This project was developed without access to Termux or an Android device — see [`CLAUDE.md`](CLAUDE.md) for exactly how it was tested anyway, and what that does and doesn't prove.

## Install

```bash
curl -sL https://raw.githubusercontent.com/arinadi/dexpro/master/install.sh | bash
```

`install.sh` bootstraps git/python, checks out the repo, and hands off to `install.py`, which installs the Termux packages the native session needs (`x11-repo`, `tur-repo`, `termux-x11-nightly`, `virglrenderer-android`, `pulseaudio`, `dbus`, `xfce4`, `xfce4-terminal`) and links the `dexpro` launcher onto `PATH`.

## Usage

```bash
dexpro
```

| Screen | What it does |
|---|---|
| Start / Stop | Native desktop session lifecycle (wake-lock → audio → GPU profile → X11 → session) |
| Update | Whole-repo `git pull --ff-only` (falls back to `fetch` + `reset --hard origin/master`), with a Restart button to relaunch on the new code |
| Boxes | Create / enter / export / backup / remove `dexpro-box` containers |
| Doctor | Native + per-container health checks (including dexpro's own install health — Textual importable, launcher resolves, required Termux packages present — plus duplicate-tool, Electron `--no-sandbox`, and font checks), with a Fix-all action |
| Backup | Lists every backup (native + per-container) with Backup / Restore / Delete |
| Settings | Real, live-editable choices — GPU profile, storage link mode, termux-x11 rendering — saved immediately on change, plus a working Uninstall |
| Store | Curated packages + search, install/uninstall, Mirror picking, and adding custom repos — all per selected `dexpro-box` container |
| Termux | Search/install/uninstall Termux's own packages (not a container's), plus a Repos screen to enable community repos (`tur-repo` and others) |

## Architecture

Two layers (see `PRD.md` §5 for the full picture):

1. **Native layer** (`app/native/`) — `dbus-launch` + `xfce4-session` directly under Termux, GPU renderer picked by on-device benchmark (`software`/`virgl`/`zink`/`turnip`), no `proot-distro` involved.
2. **`dexpro-box` layer** (`app/box/`) — a thin, distrobox-shaped wrapper over `proot-distro`'s own CLI (container create/list/remove/backup/restore, which it already provides), adding what neither `proot-distro` nor any reference project has: host-UID-mapped real user creation, per-container package management, and a `.desktop`/binary export mechanism.

```
app/
├── native/    # session lifecycle: wakelock, audio, gpu, x11, session, lifecycle
├── box/       # dexpro-box: manager, create, user, packages, export, mirror
├── doctor/    # Doctor checks: checks, electron, duplicates, fonts
├── android/   # storage auto-linking, scheme-based app bridging
├── screens/   # Textual screens (one per feature area above)
├── backup.py  # native home + container backup/restore
├── config.py  # KEY=value per-device settings
└── const.py   # paths and names
```

## Development

See [`CLAUDE.md`](CLAUDE.md) — it covers the local test setup, the Podman dev container that stands in for a real Termux device, and every environment-specific gotcha found while building this (several real bugs only surfaced by actually running the code against a real `proot-distro` CLI, not by reasoning about it).
