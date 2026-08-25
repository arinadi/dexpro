# dexpro Audit — TUI Polish & Feature Parity vs XLabs / dextop

Date: 2026-08-25
Scope: compare dexpro's actual shipped TUI and wired features against `D:\XLabs` (Python/Textual, same stack, closest direct comparison) and `D:\dextop` (bash, the project XLabs itself was informed by). Everything below is sourced from reading the actual code in all three repos side by side — no guessing from docstrings or PRD claims alone.

## TL;DR

dexpro's **backend logic is in good shape** — a lot of it is faithfully ported from XLabs/dextop and unit-tested. The disappointment is real but it's not "the logic is wrong" — it's two separate problems:

1. **The TUI layer is visibly unfinished.** dexpro's `app.tcss` is 29 lines; XLabs' is 284. No tooltips, no color-coded status, no toasts, no keyboard bindings, no confirm-dialog explanations, flat single-row button grids that don't group related actions.
2. **Several fully-built, tested backend modules are never called from anywhere a user can reach.** This is the bigger issue: it's not unfinished code, it's finished code with no door into it. `app/android/storage.py` (dextop's storage auto-linking, fully ported), `app/doctor/duplicates.py`, `app/doctor/electron.py`, `app/doctor/fonts.py` (all XLabs ports, all unit-tested) are dead weight from the user's perspective — never imported by `checks.py`, never imported by any screen. `app/box/mirror.py`'s mirror-picking and `add_custom_repo` are in the same state. `app/backup.py::restore_native_home/backup_container/restore_container` exist and work, but the Backup screen only ever calls `backup_native_home`.

The pattern: build the backend module, unit-test it, then stop before wiring the screen. Closing that gap is higher-value than re-skinning the CSS, though both matter.

## 1. TUI polish — direct comparison

| Aspect | dexpro | XLabs |
|---|---|---|
| `app.tcss` size | 29 lines | 284 lines |
| Button tooltips | none | `MainScreen.TOOLTIPS` on every button |
| Button color variants (`success`/`warning`/`error`) | only `Uninstall`, `Remove`-confirm, `Create`-confirm | Start(success)/Stop(warning)/Reset(error)/Install(success)/Uninstall(error) throughout |
| Toast notifications (`self.notify(...)`) | none anywhere | used for "no selection", "no container", warnings |
| Confirm dialogs | bare message string (`ConfirmScreen("Remove container 'x'?")`) | title + multi-line explanation + custom `confirm_label` (e.g. "This deletes the entire container... Your Termux home is untouched.") |
| Colored log output | plain `logger.write(...)`, no markup | Rich markup throughout: `[bold green]Desktop started.[/bold green]`, `[red]...[/red]` |
| Keyboard bindings | none declared on any screen | `BINDINGS = [("escape", "back", "Back")]`, `("q", "app.quit", "Quit")` |
| Table styling | plain `DataTable`, no zebra striping | `ScrollableTable(..., zebra_stripes=True)` |
| Button row layout | single flat `Grid` per screen | grouped `.row2`/`.row3` classes, destructive actions get wider gutter ("a mistap lands on the neighbour" — documented reasoning in the CSS itself) |
| Section dividers in forms | none — Settings is a flat list of Input fields | `.settings-section` muted bold dividers group related Selects |
| Enum-like settings | free-text `Input` (typo-prone: `GPU_PROFILE`, `AUDIO_METHOD`, `WM` are all plain text boxes) | constrained `Select` widgets |

None of this is subtle — XLabs' CSS file has inline comments explaining *why* each spacing/color choice was made (touch-target size, mistap prevention on destructive buttons next to safe ones). dexpro's CSS has none of that design pass.

## 2. Backend modules that exist, are tested, and are never called

Verified by grepping every non-test, non-`__pycache__` file in `app/` for references to each module's public functions.

| Module | Origin | Status |
|---|---|---|
| `app/android/storage.py` (`link_primary_storage`, `link_external_storage`, `ensure_standard_folders`, `link_unified_home`, `trigger_storage_permission`) | Ported from dextop's `termux-storage` | Defined, unit-tested (`test_android_storage.py`), **called from nowhere** — not `install.py`, not any screen, not Doctor. dextop auto-runs this during setup and exposes `.storage` label files; dexpro has the logic but no install-time or in-app trigger for it at all. |
| `app/doctor/duplicates.py` | Ported from XLabs' `duplicates.py` | Defined, unit-tested (`test_doctor_duplicates.py`), **not imported by `doctor/checks.py`**, no Doctor row, no Fix action. |
| `app/doctor/electron.py` | Ported from XLabs' `electron.py` (`--no-sandbox` patching) | Same — tested, never wired into Doctor or any screen. |
| `app/doctor/fonts.py` | Ported from XLabs' `fonts.py` | Same — tested, never wired. |
| `app/box/mirror.py` (`fetch_masterlist`, `measure_speed`, `pick_fastest`, `add_custom_repo`) | New for dexpro-box, same shape as XLabs' Mirror/Repos screens | Fully implemented (including the `curl -w speed_download` returncode-check fix from this session), **`store.py`'s own docstring admits it**: "Mirror/repo controls aren't wired into this screen yet." |
| `app/backup.py::restore_native_home` | New | Implemented (moves existing home aside as `.bak`, never destructive), **no button anywhere calls it.** |
| `app/backup.py::backup_container` / `restore_container` | Wraps `proot-distro backup -c zstd` | Implemented, **no per-container backup UI at all** — `backup.py` (screen) docstring says so explicitly: "Per-container backup/restore UI is left as follow-up." |
| `app/box/packages.py::uninstall` | New | Implemented, Store screen only wires `install`. |

**Doctor's own check count makes this concrete**: dexpro's Doctor (`app/doctor/checks.py`) runs exactly **7 checks** (X11 socket, GPU profile, audio, wake-lock binary, Termux:X11 installed, per-container apt lists, per-container UID mapping). XLabs' Doctor runs roughly **24** — and critically, XLabs checks things about *its own installation health*: is Textual actually installed, is the launcher on PATH, is Python present, is there internet. dexpro's Doctor checks none of that.

That last point is not hypothetical — every bug fixed earlier this session (`virglrenderer` → `virglrenderer-android`, missing `pulseaudio` package, the launcher's broken symlink resolution, the entirely-missing `install_libs()` step) is exactly the category of failure XLabs' Doctor would have caught with a friendly red row instead of a raw Python traceback in the user's terminal. **Recommendation: add self-install checks to Doctor** (textual importable, launcher resolves correctly, `x11-repo`/package groups present) — this is the highest-leverage single fix on this list.

## 3. Screen-by-screen feature comparison

### Main menu
- dexpro: Start, Stop, Boxes, Doctor, Backup, Settings — flat 2-col grid, no grouping, no tooltips.
- XLabs: Start, Stop, Update, Store, Settings, Doctor, Backup, Reset, Cache — grouped rows, tooltips, an in-app **self-update** button (`git pull --ff-only`, falls back to `fetch` + `reset --hard origin/main` on conflict, offers a Restart afterward).
- **Gap**: dexpro has no in-app update mechanism at all — the user must re-run `install.sh` manually from outside the app. Given this session's experience (multiple install.py bugs found only by the user re-running the bootstrap by hand), an in-app Update button that pulls and restarts would materially improve the update loop.
- **Not a gap, a scope difference**: dexpro's "Boxes" replaces XLabs' single-container Reset/Cache — dexpro manages N containers via `dexpro-box`, so a single Reset button doesn't map 1:1. But there's currently *no* bulk or per-box image-cache management anywhere, which XLabs has via Cache.

### Store
- dexpro: search + curated list + Install only. No Uninstall, no "Installed" filter, no mirror UI, no repo UI, despite all three backends existing (see §2).
- XLabs: Install **and** Uninstall (both disabled until a row is selected — dexpro doesn't disable Install on empty selection either, it just silently no-ops), an "Installed" filter view, a full `MirrorScreen` (Refresh/Measure/Use), and a full `ReposScreen` + `AddRepoScreen` (Add/Enable/Remove/Re-scan third-party repos).
- dextop's equivalent (`container-packages`) is simpler (bash menu) but does support enabling additional apt sources.

### Backup
- dexpro: **one button** ("Backup native home"). No restore, no delete, no list of existing backups, no per-container backup.
- XLabs: full table of backups (Name/Size/Created), Backup now / Restore / Delete, confirm dialogs with real explanatory text (e.g., Restore explicitly tells the user the current home is kept as `.bak`, not deleted), toast warnings when nothing is selected, refresh on screen resume.
- dextop: automated pre-install home backup (`dextop-backup-MM-DD-YYYY-HH-MM-SS.tar.gz`) plus documented manual re-run.
- **This is the single worst gap** in dexpro today: the backend (`app/backup.py`) already implements restore and per-container backup correctly and safely (moves-aside instead of overwriting, matching XLabs' own safety model) — it's 100% a missing-screen problem, not a missing-logic problem.

### Settings
- dexpro: 5 free-text `Input` fields (GPU_PROFILE, AUDIO_METHOD, WM, STORAGE_LINK, X11_EXTRA_FLAGS) + Save + **Uninstall button that does nothing** (shows a confirm dialog, then the handler is a bare `pass` — the docstring admits it: "wiring the real removal is follow-up"). This is worse than just missing a feature — it's a button that *looks* functional and silently isn't.
- XLabs: `Select` widgets (no typos possible), grouped under `.settings-section` dividers, a working Uninstall.
- dextop: settings are shell-level toggles (`echo audio > .dextop/dextop-audio`, `.dextop/dextop-logout`, `.dextop/dextop-update`) for audio-on-login, auto-logout-on-exit, and auto-update-on-login — all absent from dexpro's Settings screen (and from dexpro entirely; there's no equivalent of any of the three).

### Doctor
- Covered in §2. 7 checks, none about dexpro's own install/runtime health; the three ported-but-unwired modules (duplicates/electron/fonts) mean Doctor's Fix button can never remediate what those modules already know how to detect.

## 4. dextop-specific gaps (bash project, different architecture — noted separately since some of this may be intentional non-goals)

**Update 2026-08-25 — item 7 resolved.** User decided explicitly (not by omission):
- **VNC fallback: no.** Native session stays termux-x11-only. Recorded in `PRD.md`'s feature table and `build-task-phase1.md`'s Prerequisites (both previously implied it was planned/ported; neither was true).
- **Per-utility update: not applicable, by design.** dexpro is one cohesive git-versioned package, unlike dextop's separately-installed utility scripts — there is no narrower unit than the whole repo to update. Implemented as a single **Update** button on the main menu (`git pull --ff-only`, falls back to `fetch` + `reset --hard origin/master` on conflict) with a **Restart** button that re-execs the process (`os.execv`) so the new code actually loads — ported from XLabs' `run_update`/`request_restart` pattern. This was previously a real gap: dexpro had no in-app update mechanism at all.
- **Auto-login-on-open: no.** Start stays an explicit, manual tap — auto-launching a GUI session as a side effect of opening Termux was judged a surprising default, unlike dextop's own assumption of a dedicated device.

~~No alternate display server~~ / ~~no granular per-utility update~~ / ~~no auto-login convenience~~ — all resolved above, decisions made explicitly.

- **No Activity Manager mimetype/activity handoff** (`dextop-additions`): this is intentionally replaced by dexpro's own `dexpro box export` (host-side wrapper + `.desktop` entry) per the PRD's own comparison table — **this is a deliberate, reasonable redesign, not a gap.**

## 5. What's correctly *not* a gap

To avoid the audit reading as "dexpro should clone everything XLabs has":
- XLabs' `browser_screen.py`, `claude_md_screen.py`, `mcp_screen.py`, `providers_screen.py` are Claude-Code/AI-dev-workflow specific tooling — entirely outside dexpro's PRD scope (dexpro is a DeX productivity shell, not an AI dev environment manager). Not counted as gaps above.
- Docker/Podman-in-container, root access workarounds, and auto-migration from existing XLabs/dextop installs are explicit PRD Non-Goals (NG1/NG2/NG5) — correctly absent.
- dexpro's multi-container `dexpro-box` model, `dexpro box export`, and the native (non-proot) session architecture are all *more* than either reference project offers — genuinely new work, not a deficiency.

## 6. Recommended priority order

1. **Wire Doctor to self-check the install** (textual importable, launcher symlink resolves, key packages present). Directly prevents a repeat of this session's three install bugs.
2. **Finish the Backup screen**: add Restore + a backup list, using the already-working `restore_native_home`. Highest risk-reduction per line of UI code, since the backend is already correct and safe.
3. **Fix or remove the Settings Uninstall button** — a no-op that looks functional is worse than not having the button.
4. **Wire `duplicates.py`/`electron.py`/`fonts.py` into Doctor** — the detection logic and tests already exist; this is check-registration work, not new logic.
5. **CSS/polish pass**: tooltips, button variants, toast notifications, confirm-dialog copy, keyboard bindings — matches the "TUI mengecewakan" complaint most directly, but is lower-risk/lower-value than 1–4 since it doesn't fix anything that's silently broken.
6. **Store screen**: Uninstall button, Mirror/Repos screens on top of the already-built `mirror.py`.
7. ~~Decide deliberately (not by omission) on VNC fallback, per-utility update, and auto-login-on-open~~ — **done 2026-08-25**, see §4 update above.
