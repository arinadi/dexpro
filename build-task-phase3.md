# Build Task — Phase 3: App Export

Status: Draft v1
Date: 2026-08-25
Depends on: Phase 2 (`box/manager.py`, container list)
PRD refs: G2 (export sub-goal), §5.2, §7.5

## Objective

Run a `dexpro-box` container's app or binary from the host launcher — a distrobox-style export mechanism. **Confirmed net-new work**: neither XLabs nor dextop has any app-export/desktop-integration mechanism today (grepped both trees in the initial research pass — zero matches for the concept, only Python's literal shell `export FOO=` env-var syntax in XLabs).

## Reference: how `distrobox-export` actually does it (confirmed from source/docs research)

**Note**: distrobox's core was rewritten from POSIX shell to Go as of v1.8.2.5 (2026-04-27) — the standalone shell script no longer lives at repo root; invocation now goes through the unified `distrobox` binary. Confirmed CLI surface:

```
distrobox-export --app <name|/path/to/x.desktop> [--export-label <l>] [--extra-flags "..."] [--delete] [-nf/--enter-flags "..."] [--sudo]
distrobox-export --bin <abs_path> --export-path <dest_dir> [--extra-flags "..."] [--delete]
distrobox-export --list-apps | --list-binaries
```

- **App export**: copies the container's `.desktop` file + referenced icon to the host (`$HOME/.local/share/applications` and `$HOME/.local/share/icons` — corroborated by docs/long-standing convention; not verified against literal Go source, which wasn't reachable during research), rewrites `Exec=` to prefix `distrobox enter -n <container> -e ...`.
- **Binary export**: generates a wrapper script at `--export-path` (commonly `~/.local/bin`) that internally runs `distrobox enter -e -n <container> -- <binary> "$@"`.
- **Removal**: re-run the same export command with `--delete`.

`dexpro box export` adapts this exact shape, substituting `proot-distro login` for `distrobox enter`.

## Proposed module layout (adds to Phase 2's `app/box/`)

```
app/
├── box/
│   └── export.py          # Task 1
└── screens/
    └── export_screen.py   # Task 3
```

## Tasks

### 1. `box/export.py`

**Binary export** — `dexpro box export <name> --bin <path-inside-container> [--export-path ~/.local/bin]`:
- Generate a wrapper script at `<export-path>/<binary-name>`:
  ```sh
  #!/data/data/com.termux/files/usr/bin/bash
  exec proot-distro login <name> --shared-tmp -- <path-inside-container> "$@"
  ```
- `chmod +x` the wrapper.

**App export** — `dexpro box export <name> --app <name-or-desktop-file>`:
1. Locate the container's `.desktop` file: search `/usr/share/applications`, `~/.local/share/applications` **inside the container** (`proot-distro login <name> -- find ...`).
2. Copy it, and its referenced icon, to the host: `~/.local/share/applications/` and `~/.local/share/icons/` respectively.
3. Rewrite the copied file's `Exec=` line to prefix `proot-distro login <name> --shared-tmp -- <original Exec value>` — mirrors distrobox's Exec-rewrite approach.
4. **Reuse XLabs' `desktopfiles.py` module** (`find_desktop_file_for_binary`, `desktop_exec_has`, `patch_desktop_exec`, surfaced via the `browser.py`/`electron.py` research) as the closest existing prior art for `.desktop` manipulation in either reference codebase — it already solves "find/patch a `.desktop` file's `Exec=` line" for XLabs' own Electron `--no-sandbox` patching, which is structurally the same operation this needs.

**Removal**: `--delete` flag removes the generated wrapper / copied `.desktop` file / copied icon — mirrors distrobox's own removal UX exactly.

**Discovery**: `dexpro box list-exports` split into `--list-apps` / `--list-binaries` (naming lifted directly from distrobox's own flags, for user familiarity if they've used distrobox before).

### 2. Document the fidelity tradeoff (PRD §7.5) in user-facing help text

An exported app still crosses the ptrace boundary for **its own** syscalls — export only avoids nesting a second full GUI session inside the container (which was the actual perf-killer per PRD §1's root-cause analysis). It does not make the exported app itself native-speed. State this plainly in `--help` output and any TUI tooltip, so it isn't oversold as a full fix.

### 3. `screens/export_screen.py`
Per-container "Export" action: list `.desktop` files and known binaries found inside the selected container (via the discovery logic from Task 1), multi-select, confirm via Phase 1's `ConfirmScreen`.

## Testing

- Export a known GUI app (e.g. a text editor) from a container; launch it from the host `~/.local/bin` wrapper *and* via the generated `.desktop` entry in a file manager; confirm it renders correctly through Phase 1's native X11 session.
- Confirm `--delete` fully removes the wrapper, `.desktop` file, and icon — no orphaned files.
- Confirm a re-export after `--delete` is idempotent (doesn't error on "already exists" from a partial prior cleanup).

## Exit criteria

An exported app launches and renders through the native session (Phase 1) without the user manually entering the container first — one tap/command from the host.

## Verified on-device (Podman dev container, 2026-08-25)

Implementation and testing happened against the real `proot-distro` v5.8.0 CLI, same as Phase 2. Real finding, not hypothetical:

- **`list_desktop_files()`'s multi-directory search had a real bug**: joining the per-directory `find` invocations with a bare space (`" ".join(...)`) produced one malformed command — the shell parsed the second `find /root/.local/share/applications ...` as extra arguments to the *first* `find` call, not a separate command. This silently returned an empty list against a container that genuinely had a `.desktop` file seeded in it (`/usr/share/applications/fakenvim.desktop`) — caught only by running it for real, not by local unit tests (which only exercise the "proot-distro missing entirely" path). Fixed by joining with `;` instead, and extracted the script-building into `desktop_find_script()` so the separator itself has a dedicated unit test now (`test_desktop_find_script_joins_commands_with_a_separator`).
- **Confirmed working end-to-end after the fix**: seeded a synthetic `.desktop` file inside a real `proot-distro` container, ran discovery (found it), ran `export_app()` (copied it to the host, correctly rewrote `Exec=nvim %F` to `Exec=proot-distro login exptest --shared-tmp -- nvim %F`, preserved `Name=`/`Icon=`/`Type=`, added the `X-Dexpro-Container=exptest` ownership marker), confirmed `list_exports()` reflects it, and confirmed `delete_app_export()` removes it and refuses to touch anything it didn't create.

Not yet exercised: icon export (the seeded test `.desktop` referenced `Icon=nvim`, but the container had no actual icon file at any of the conventional paths this module checks, so the icon-copy path never actually ran against real icon bytes — only its "nothing found, skip" branch); binary export (`export_bin`/`wrapper_script`) against a real invocation of the resulting wrapper script; and — same limitation as Phase 1 — actually launching an exported GUI app and confirming it renders through the native session. That last one is this phase's actual Exit Criteria and remains unverified, same class of gap as Phase 1's own unresolved X11-rendering question.
