# Build Task — Phase 4: Doctor / Backup / Bench Parity

Status: Draft v1
Date: 2026-08-25
Depends on: Phase 1 (native/gpu.py, native/audio.py), Phase 2 (box/manager.py, box/packages.py, box/user.py)
PRD refs: G4, §5.3, §6

## Objective

Re-scope XLabs' operational tooling (Doctor, Backup, Bench, Settings-adjacent checks) across **the native layer and however many `dexpro-box` containers exist** — not just one Debian container, which is XLabs' current single-container model.

## Proposed module layout (adds to `app/`)

```
app/
├── doctor/
│   ├── checks.py     # Task 1/2 — Issue model + native/per-container checks
│   ├── fixes.py       # auto-fix implementations
│   ├── electron.py    # Task 3 — ported
│   ├── duplicates.py  # Task 4 — ported/adapted
│   └── fonts.py       # Task 5 — ported
├── backup.py           # Task 6
└── screens/
    ├── doctor.py       # Task 8
    └── backup.py       # Task 8
```

## Tasks

### 1. `doctor/checks.py` — core model
Port XLabs' `Issue` NamedTuple (`name`, `ok`, `detail`, `fix`, `unknown`) directly — it's a clean, minimal model with nothing proot-specific about its shape.

**Native-layer checks**:
- X11 socket alive (reuse Phase 1's `wait_for_x11` connect-check as a standing health check, not just a startup gate).
- GPU renderer matches the persisted profile (`native/gpu.py`'s `GPU_PROFILE`) — catch drift if a device update changes available renderers.
- PulseAudio method still working — re-run `audio.py`'s tone-probe as a Doctor check, not only at session start (a method that worked at install time can silently break after a Termux/PulseAudio update).
- Wake-lock held during an active session.
- **New check, not in either reference project**: Termux:X11 app installed with the correct signing variant — catches the universal-vs-sharedUid / GitHub-vs-F-Droid key mismatch pitfall identified in Phase 1's prerequisites. This is a real, previously-undocumented-in-either-project failure mode worth surfacing explicitly rather than leaving users to debug a cryptic install failure.

### 2. Per-container checks
Loop over `dexpro box list` (Phase 2's `box/manager.py`):
- Apt lists present (`lists_present()`, ported from XLabs' `packages.py`).
- Package manager healthy (basic `apt-get check` or equivalent).
- User exists and is host-UID-mapped — re-run Phase 2's ownership test (`ls -l` on the container rootfs matching real host UID) as a standing Doctor check, not just a one-time creation-time test.
- Sudoers config matches what was chosen at creation (opt-in sudo from Phase 2 Task 3).

### 3. Electron `--no-sandbox` patching
Port XLabs' `electron.py` logic verbatim — detects Electron apps via a `chrome-sandbox` helper binary next to the resolved executable, patches the `.desktop` `Exec=` line to add `--no-sandbox` (proot can't back Chromium's SUID/userns sandbox). **Scope per-container** — each container's Electron apps need the same patch independently; loop the existing per-app logic over every container instead of one fixed target.

### 4. Duplicates
Port XLabs' `duplicates.py` `TERMUX_DUPLICATES` dict (Termux package name → binary name, ~15 entries: `nodejs→node`, `rust→rustc`, `neovim→nvim`, etc.), deliberately excluding anything dexpro itself needs (python, git, proot-distro, termux-x11-nightly, pulseaudio, graphics packages — same exclusion rationale as XLabs). **Adapt the scope**: XLabs checks "Termux vs the one container"; dexpro needs "Termux vs any dexpro-box container," so the check needs a container selector or a "check all" mode. Same double-verification discipline as XLabs: confirm both "is it installed in Termux" (`dpkg-query`) and "does the target container actually provide it" (`command -v` run inside via a generated script) before offering removal — never assume.

### 5. Fonts
Port XLabs' `fonts.py` near-verbatim: `fonts-noto-color-emoji`, `fonts-firacode`, `fc-cache -f`, then activate Fira Code 11 as the `xfce4-terminal` font via a surgical INI-section patch (`_patch_ini_section`, doesn't clobber other user settings). **Scope change**: this now applies to the native layer's own font cache/config (`~/.config/xfce4/terminal/terminalrc` directly), not inside a container — simpler than the source, since there's no proot boundary to cross.

### 6. `backup.py` — two scopes
- **Native home backup**: direct `tar czf`, no container involved — genuinely simpler than XLabs' approach, since XLabs' `--link2symlink` hardlink-emulation concern (why it runs `tar` *inside* the container rather than copying from the host) doesn't apply to a native filesystem. A straightforward host-side `tar` is correct here.
- **Per-container backup**: prefer `proot-distro backup <name> -c zstd` (confirmed v5.x flag, supports gzip/bzip2/xz/zstd/none) over hand-rolling XLabs' own tar-inside-container approach — **upstream already provides this**, don't reimplement it. Restore likewise via `proot-distro restore`.
- Both: write to a temp path first, `move` into the final backup directory only once complete (XLabs' atomic-write pattern — an interrupted backup should never show up as a listed, restorable backup). Restore should move any existing target aside first (XLabs' `home.bak` pattern), never destructively overwrite outright.

### 7. Bench
Directly reusable from Phase 1's `native/gpu.py` — no new logic needed. Doctor's "Bench" action simply re-invokes it on demand (equivalent to XLabs' `--rebench`).

### 8. TUI: `screens/doctor.py`, `screens/backup.py`
Port XLabs' pattern: one screen, full checkup, each issue shown as ● present / ○ missing / **?** unknown. `Fix (N)` aggregate action repairs everything auto-fixable in one pass. Every fix/destructive action logged and goes through Phase 1's `ConfirmScreen` where it isn't purely additive (e.g. removing a duplicate, patching a config file the user might have hand-edited).

## Testing

- Seed deliberate breakage (corrupt `terminalrc`, remove a container user, break a container's apt lists) and confirm Doctor correctly identifies **and** fixes each seeded issue via `Fix (N)`.
- Backup/restore roundtrip for both native home and at least one container, confirming restored content matches pre-backup state.
- Confirm the Termux:X11 signing-variant check correctly flags a deliberately mismatched install (e.g. sharedUid APK with a GitHub-signed Termux, or the reverse).

## Exit criteria

- Doctor screen surfaces accurate ● / ○ / ? status across the native layer **and** all `dexpro-box` containers.
- `Fix (N)` resolves all auto-fixable seeded issues in one pass.
- Native and container backups are both independently restorable without data loss.
