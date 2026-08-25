# Build Task — Phase 1: Native Desktop Session

Status: Draft v1
Date: 2026-08-25
Depends on: nothing (first phase)
PRD refs: G1, G6, §5.1, §7.1, §7.2, §7.4, §10 (addendum)

## Objective

`dexpro start` boots a desktop session **directly under Termux, with zero `proot` in the GUI critical path**, using benchmark-driven GPU renderer selection. This alone is the direct fix for the reported DeX performance complaint (root cause: `proot`'s ptrace-per-syscall overhead scaling with GUI syscall volume — see PRD §1).

## Prerequisites

- Termux app — GitHub Releases or F-Droid (note: these are separately signed; pick one and stay on it, don't mix update channels).
- **Termux:X11** app — GitHub Releases `nightly` tag only. Two APK variants: `-universal-debug.apk` (standard) vs `-universal-sharedUid-debug.apk` (avoids CPU throttling, but requires a Termux build signed to match — GitHub build, not F-Droid's differently-signed build). **Pick the matching pair and document it** — this is a real, easy-to-hit mismatch pitfall, not a hypothetical.
- Termux packages: `x11-repo` (enables the repo), then `termux-x11-nightly`, `virglrenderer`/`virglrenderer-android`, `xorg-server-xvfb` (fallback display server), `pulseaudio-utils`, `dbus`, plus the chosen WM/DE package set (§ Task 8).

## Spikes to resolve before/during implementation (do not assume — verify on-device)

| Spike | Why it's open | How to resolve |
|---|---|---|
| **Device GPU vendor** (Adreno vs Mali/Exynos) | zink/Turnip are Adreno-only per current docs; Mali falls back to virgl/software | Check `getprop ro.hardware`/`ro.board.platform`/`ro.chipname` on the actual device; no single confirmed key found in research — try several, verify against known SoC name |
| **DeX docked-state detection** | No confirmed shell-level method exists; documented APIs are Java/app-level (`UiModeManager`, Samsung Knox broadcasts) | Try `dumpsys display`/`wm density` under Termux's unprivileged UID (`u0_a###`) — unconfirmed whether it returns non-empty output without `adb shell`'s elevated context; if empty, ship v1 without auto-detection (manual profile toggle) |
| **Is `.ICE-unix` ownership fix still needed natively?** | XLabs' `prepare_ice_dir()` host-side-chmod workaround exists specifically because proot mis-reports ownership; that reason doesn't apply once there's no proot in this path | Try running the session without it first; only add if `xfce4-session` actually fails to register children |
| **WM choice: XFCE vs i3** | Whole point of native layer is minimizing syscall volume; XFCE is the safe default (matches both reference projects) but i3 (dextop already optionally supports it) may benchmark meaningfully lighter | Bench both on-device with the same window-drag/panel-interaction timing script from Task 10; XFCE ships as default regardless unless i3 wins by a wide, reproducible margin |
| **Does Termux-packaged `xfce4-session`/X11 client libs work against a generic X11 socket?** (new, found during Phase 1 dev-container validation) | In the Podman dev container (`docker/dev/`, real `pkg install`'d `xfce4`), `xfce4-session` failed with `Cannot open display: .` against a real X11 socket (WSLg's, bind-mounted correctly, confirmed reachable) with `DISPLAY=:0` exported — root cause not isolated (candidates: Termux's X11 packages carry Android-specific patches that don't behave like stock Debian/Ubuntu builds; `dbus-launch`'s child process not inheriting `DISPLAY` as expected under `nohup ... &`; something WSLg/Podman-machine-specific). Neither XLabs nor dextop's own dev tooling exercises this exact path (XLabs' `dev.sh` runs its desktop *inside proot-distro's Debian*, i.e. real Debian X11 packages, not Termux's own — sidestepping this question entirely) | Needs isolation: test with `xterm`/`xclock` (simpler than a full session) against the same socket first; check whether `dbus-launch --exit-with-session` truly propagates `DISPLAY` to its child in this environment; ultimately must be confirmed on the real device against `termux-x11`'s actual socket, which is a different code path (`termux-x11 :1` app-paired socket) than the generic X11 socket this dev-container test used |

None of these are decided by this document — they're implementation-time verification steps, flagged explicitly so they aren't silently assumed.

## Proposed module layout

```
dexpro/
├── dexpro                  # launcher shim (bash, mirrors XLabs' `xlabs` launcher)
├── install.sh / install.py # bootstrap installer (two-stage, mirrors XLabs)
├── pyproject.toml          # Python 3.11+, textual>=8.2
└── app/
    ├── app.py              # DexproApp(App) — Textual entrypoint
    ├── const.py            # paths/names (mirrors XLabs' const.py)
    ├── config.py           # KEY=value .env reader/writer (port XLabs' config.py near-verbatim)
    ├── screens/
    │   ├── common.py       # ActionScreen (@work(thread=True) runner + throttled progress log),
    │   │                   #   ConfirmScreen(ModalScreen[bool]) — port XLabs' pattern verbatim,
    │   │                   #   these are shared scaffolding every later phase reuses
    │   └── main_screen.py  # Grid-of-buttons menu (Grid, not Horizontal — avoids XLabs' known overflow issue)
    └── native/
        ├── wakelock.py     # Task 2
        ├── audio.py        # Task 3
        ├── gpu.py           # Task 4
        ├── x11.py           # Task 5
        ├── session.py       # Task 6
        └── lifecycle.py     # Task 7/8 — start/stop chain, owned by App.on_mount
```

## Tasks

### 1. Repo scaffold
- `pyproject.toml`: `textual>=8.2` (current stable at research time: 8.2.8), Python ≥3.11.
- `dexpro` launcher (bash): resolves interpreter, execs `python -m app.app "$@"` — mirrors XLabs' `xlabs` launcher shape.
- `install.sh`/`install.py`: two-stage bootstrap (curl→git+python+repo checkout, then full installer) — same shape as XLabs, content is new.
- `ruff.toml` + minimal `pytest` smoke test for `const.py`/`config.py` — no lint/test infra exists yet; this phase is where it's stood up.

### 2. `native/wakelock.py`
- Wrap `termux-wake-lock` / `termux-wake-unlock` — **confirmed zero args, ships in core `termux-tools`, no Termux:API dependency** (verified from `termux-wake-lock.in` source: `am startservice --user $TERMUX__USER_ID -a com.termux.service_wake_lock com.termux/com.termux.app.TermuxService`).
- **Confirmed necessary, not optional**: Termux's foreground service does NOT itself acquire a wakelock (`TermuxService.java`'s `onCreate()` doesn't; the wakelock is only acquired on the explicit `ACTION_WAKE_LOCK` intent this command sends). Skipping this call means the session can be doze-throttled mid-use.
- Acquire at session start, release at session stop. Log a non-fatal warning if the command fails (matches XLabs' `acquire_wake_lock()` behavior — don't block startup on it).

### 3. `native/audio.py`
- Port XLabs' `ensure_server()` four-method probe **pattern**, not its code: try unix → unix-shm → tcp → tcp-shm, each verified end-to-end with a generated 440Hz test tone (`paplay`, checked for `"OK play"` in output — not just "module loaded").
- **Genuine adaptation, not a port**: XLabs writes `/etc/pulse/client.conf` *inside the proot'd container*. There is no container here — config lives directly at `~/.config/pulse/client.conf` (or the server is launched directly in the native environment). This is a real architectural difference from the source, not a copy.
- Persist the chosen method in `config.py` (`AUDIO_METHOD=`) so it isn't re-probed every start.

### 4. `native/gpu.py`
- Port XLabs' `bench.py`/`isolation.py` **"measure, don't guess"** methodology: run `glmark2` scenes (`build`, `texture`, `shading`, 2s each — XLabs' exact scene/timing choice) per candidate renderer, keep whichever wins on-device.
- **Updated candidate list** (per current termux-x11 hardware-acceleration docs, supersedes XLabs' older virgl/ANGLE/zink/software list):
  | Renderer | Env vars | Constraint |
  |---|---|---|
  | `software` | `LIBGL_ALWAYS_SOFTWARE=1` | universal fallback |
  | `virgl` | `GALLIUM_DRIVER=virpipe` + `virgl_test_server_android` running | universal fallback, older/proven |
  | `zink` | `GALLIUM_DRIVER=zink`, `MESA_GL_VERSION_OVERRIDE=4.3COMPAT`, `MESA_GLES_VERSION_OVERRIDE=3.2`, `ZINK_DESCRIPTORS=lazy` | **Adreno-only** per docs |
  | `turnip` | `MESA_LOADER_DRIVER_OVERRIDE=zink`, `TU_DEBUG=noconform`, requires `mesa-vulkan-icd-freedreno-dri3` | **Adreno 610+ only**, native Vulkan passthrough |
  | `freedreno/kgsl` | `MESA_LOADER_DRIVER_OVERRIDE=kgsl` | experimental, **reported to break XFCE** — exclude from auto-bench, manual opt-in only if offered at all |
- Skip Adreno-only candidates (zink, turnip) unless the GPU-vendor spike (see table above) confirms Adreno. No ANGLE-on-Android path was found in current termux-x11 docs — drop it from the candidate list (XLabs' original ANGLE reference is stale).
- Persist result to `config.py` (`GPU_PROFILE=`); `--rebench` flag forces re-run.

### 5. `native/x11.py`
- Don't use the single-line `termux-x11 :1 -xstartup "..."` convenience form — it fire-and-forgets the session, which doesn't give the TUI a state to track. Instead, mirror XLabs' more robust split:
  1. Launch `termux-x11 :1` alone.
  2. **Poll actual socket connect** (XLabs' `wait_for_x11` approach — checking the socket actually accepts, not just that the file exists) before proceeding.
- Diagnostic flags to expose in Settings (Phase 5) for known-broken devices: `-legacy-drawing`, `-force-bgra` (black-screen/swapped-color devices, per XLabs' own device-specific flag precedent), `TERMUX_X11_DEBUG=1`.

### 6. `native/session.py`
- Session launch script, adapted from XLabs' `SESSION_SCRIPT` — **key structural change: no `proot-distro login` wrapper, runs directly as the Termux user.**
- Sets: `DISPLAY=:1`, `PULSE_SERVER=<from audio.py's chosen method>`, `NO_AT_BRIDGE=1`, creates `XDG_RUNTIME_DIR` (mode `0700`) if absent.
- GPU env vars injected from `gpu.py`'s persisted profile (Task 4).
- Uses `xfce4-session` explicitly, **not** `startxfce4` — same reasoning as XLabs: `startxfce4` no-ops when `DISPLAY` is already set (prints "X server already running", hands to xinitrc, session never actually launches).
- Wrap in `dbus-launch --exit-with-session "$SESSION"` only if `DBUS_SESSION_BUS_ADDRESS` is unset (matches both XLabs and dextop's `container_session()` — this part genuinely is shared prior art, not proot-specific).
- Do **not** pre-implement the `.ICE-unix` ownership workaround (XLabs' `prepare_ice_dir`) — it's a proot-ownership-translation fix that may not apply natively. See spike table.

### 7. Start chain (`native/lifecycle.py`)
Adapted `START_STEPS`, in order: **stop (idempotent, unconditional)** → wake-lock → `audio.ensure_server` → GPU profile load (bench on first run) → `start_x11` → `wait_for_x11` → `start_session`.

Implement as a Textual `@work(thread=True, exclusive=True)` worker **owned by `DexproApp.on_mount`**, not any individual Screen — per Textual's current guidance, a persistent background service should live at the App level so it survives screen navigation (Textual has no dedicated "background service" doc section, but `install_screen`/`SCREENS` keeping screens alive for the app's lifetime, plus App-level `on_mount`/`on_unmount` as the documented lifecycle hooks, is the closest idiomatic pattern). Marshal any UI updates via `self.app.call_from_thread(...)` (mandatory for thread workers, not optional).

### 8. Stop chain
Innermost-first teardown, mirroring both reference projects' shared philosophy: kill session process (TERM then KILL) → stop X11 → stop audio → wake-unlock → sweep leftover processes. **Verify with `pgrep` rather than just claiming success** — this is XLabs' explicit design principle for Stop Desktop and should carry forward as-is; a stale process is exactly what breaks the next start.

### 9. Minimal diagnostics
Full Doctor is Phase 4, but this phase needs a `collect_diagnostics()`-equivalent that auto-runs on start failure (matches XLabs' pattern) — dump X11 socket state, GPU renderer chosen, audio method, wake-lock status, session process exit code. Failures need to be debuggable from day one, not deferred to Phase 4.

## Testing / Verification

- Stress test: start/stop 10x in a row, verify zero orphaned processes via `pgrep` after each stop.
- **Operationalizes PRD §4 Success Metrics**: record `glmark2` scores + a fixed window-drag/panel-interaction timing script on this native session, vs. a reference full-proot session (e.g. `proot-distro login <name> -- xfce4-session` as an approximate stand-in, or a temporary XLabs install for direct A/B) — same device, same DeX dock, same GPU profile where applicable.
- No project lint/test/build infra exists yet — this phase stands it up (`ruff`, minimal `pytest`); say so explicitly in any status update rather than skipping verification silently.

## Exit criteria

- `dexpro start` boots a usable native XFCE session with GPU acceleration on the reference device.
- `dexpro stop` tears down cleanly and verifiably (zero orphaned processes).
- Wake-lock held for the session's duration.
- GPU profile persisted and reused on next start without re-benchmarking (unless `--rebench`).

## Verified on-device (real device, 2026-08-25)

First actual Tier 3 (real device) data point for this project — everything before this was Tier 1/2 only.

- `install.py`'s single-batch `pkg install -y <6 packages>` failed with "Unable to locate package" and installed nothing (not even the packages that would have resolved fine). Root cause: the package list included bare `virglrenderer`, which is not a valid Termux package name — `app/native/gpu.py`'s `virgl` preset already assumed the correct name (`virgl_test_server_android` binary, shipped by package `virglrenderer-android`), confirmed by cross-referencing XLabs' own `install.py` (`D:\XLabs\install.py`), which uses `virglrenderer-android` and documents the exact same batch-failure trap: "One unavailable name fails the whole line and takes every other package in it down too."
- Fix applied: renamed to `virglrenderer-android`, and restructured `install_packages()` into labeled groups with per-package retry on group failure (same pattern XLabs uses), so one bad/unavailable name can no longer take down unrelated packages in the same batch.
- Not yet re-confirmed on the real device (only Tier 1: ruff + `tests/run_tests.py`, both pass) — next real-device install run should confirm the corrected package list resolves.
- A/B bench numbers recorded against a full-proot reference session (even if the improvement threshold itself isn't fixed yet — PRD §4 leaves the exact number open until a baseline exists).
