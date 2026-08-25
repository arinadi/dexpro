# Build Task — Phase 2: `dexpro-box` Core

Status: Draft v1
Date: 2026-08-25
Depends on: Phase 1 (reuses `screens/common.py`'s `ActionScreen`/`ConfirmScreen`)
PRD refs: G2, §5.2, §10 (addendum)

## Objective

A distrobox-style helper for isolated dev/CLI containers, built **on `proot-distro` v5.x** — not a reimplementation of image acquisition (both reference projects effectively reinvent parts of what proot-distro v5.x now does natively).

## Critical correction from research — read before implementing

**`proot-distro` was rewritten in Python as of v5.x (current: v5.8.0, released 2026-08-22).** It is no longer the classic bash tool with a fixed distro-plugin list — it now pulls **any Docker/OCI image** directly from registries, like a minimal Docker client. It already ships, out of the box:

- `install [-n/--name] [-a/--architecture] (IMAGE|PATH|URL)` — any Docker ref (`ubuntu:24.04`, `ghcr.io/foo/bar:latest`) or local tarball/OCI-layout path
- `login [-u/--user] [--shared-tmp] [--shared-home] [--shared-x11] [-b/--bind] [--emulator] [--kernel] [--hostname] [-w/--work-dir] [-e/--env] [-d/--detach] [--get-proot-cmd] CONTAINER [-- COMMAND]`
- `remove`/`rm`, `list`/`li`/`ls`, `rename`
- `backup [-o] [-c {gzip,bzip2,xz,zstd,none}] [-v]`, `restore`, `reset` (re-pulls from stored image ref — fails for tarball-only installs)
- `search`, `build` (Dockerfile→OCI, no daemon), `push`, `run`, `ps`/`kill` (for `-d` detached sessions), `clear-cache`

Rootfs path: `$PREFIX/var/lib/proot-distro/containers/<name>/rootfs/`, manifest at `.../containers/<name>/manifest.json`. Legacy pre-5.x path (`installed-rootfs/<name>`) auto-migrates on first login.

**Do not port dextop's `container-image` manual tar.xz extraction, or reimplement `list`/`backup`/`restore`/`rename` — they already exist upstream.** This shrinks Phase 2's actual scope to what's genuinely missing:

1. **Host-UID/GID-mapped real user creation.** `proot-distro login --user` is ptrace UID-*faking* via `--change-id` — it changes what UID the process appears to run as, it does not create a real container user account with matching passwd/home ownership. dextop's own `container-user` automated path hardcodes `1000:1000`, which doesn't map to the actual host UID either — this is a gap in **both** reference projects, not something to copy from either.
2. **Package-management convenience wrapper** — proot-distro doesn't have an apt-search/install UX; that's still dexpro's job, per-container.
3. **DNS resolution inside a fresh container** — proot containers don't inherit host DNS automatically (this is why XLabs ships a Doctor "DNS" fix). dextop's own `termux-system::add_network()` writes `nameserver 1.1.1.1` / `1.0.0.1` (Cloudflare) into freshly-scaffolded containers — apply the same fix proactively at `dexpro box create` time instead of waiting for a Doctor complaint.
4. Phase 3 (export) depends on this phase but is a separate document.

## Version guard

Pin a minimum tested `proot-distro` version in `box/manager.py` (check `proot-distro --version` at startup, warn if below baseline). **Do not assume backward compatibility with pre-5.x installs** — the CLI surface changed substantially with the rewrite.

## Proposed module layout (adds to Phase 1's `app/`)

```
app/
├── box/
│   ├── manager.py    # Task 1 — subprocess wrapper over proot-distro CLI
│   ├── create.py     # Task 2 — create + post-install hooks (init, DNS)
│   ├── user.py       # Task 3 — host-UID-mapped user creation (new work)
│   └── packages.py   # Task 4 — per-container apt wrapper (ported from XLabs)
└── screens/
    └── box_manager.py  # Task 5
```

## Tasks

### 1. `box/manager.py`
Thin subprocess wrapper over `proot-distro install/list/remove/rename/backup/restore/search`. Use `--get-proot-cmd` for introspection/debugging (prints the assembled `proot` invocation without running it — useful for Doctor/support output in Phase 4). Version-check at startup per the guard above.

### 2. `box/create.py`
`dexpro box create <name> [--image ubuntu:24.04]` → `proot-distro install <image> --name <name>`.

Post-install hook chain (mirrors dextop's `container-initialization` exactly — this part of dextop is simple and correct, port near-verbatim):
```
apt update
apt full-upgrade
apt install locales
locale-gen en_US.utf-8
```
Then write `/etc/resolv.conf` inside the container with `nameserver 1.1.1.1` / `nameserver 1.0.0.1` (dextop's exact DNS choice) — proactive, not reactive-only-via-Doctor.

**Spike**: whether `--shared-tmp`/`--shared-home` should be dexpro-box's default `login` flags. dextop's own need for a shared-tmp-equivalent came from its hand-rolled bind-mount model, which doesn't carry over 1:1 to proot-distro v5.x's own flag semantics — evaluate against what each container actually needs (e.g. `--shared-tmp` likely useful for X11 socket access if an exported app needs it in Phase 3; don't default it on for pure CLI toolboxes without reason).

### 3. `box/user.py` — new work, not a port
1. Resolve real host UID/GID: `os.getuid()` / `os.getgid()` from the Termux-side Python process.
2. Create a matching container user: `adduser --uid <uid> --gid <gid> --gecos "" --disabled-password <name>`, run through `proot-distro login <container> -- ...` (adduser flag shape lifted from dextop's `user_interactive()`, corrected to actually pass the real UID instead of dextop's hardcoded 1000).
3. Passwordless sudo (dextop's `user_superuser()` pattern: add to `sudo` group + `/etc/sudoers.d/<user>` `NOPASSWD:ALL`) is **opt-in, not default** — explicit security deviation from dextop, which defaults it on. Surface as a `--sudo` flag or a confirm prompt, not silent.
4. `user_runtime()`-equivalent: create `/run/user/<uid>` mode `0700` (dextop does this; carry forward, it's correct and non-controversial).

### 4. `box/packages.py`
Port XLabs' `packages.py` approach closely — it's well-designed and directly reusable as a *pattern*:
- `SAFE_TERM = ^[a-z0-9][a-z0-9.+-]{0,63}$` allow-list gate on all package names/search terms (shell-injection defense by rejection, not escaping) — carry forward verbatim, it's a security control, not a style choice.
- `DEBIAN_FRONTEND=noninteractive apt-get install/remove -y "$@"`.
- `lists_present()` check (`/var/lib/apt/lists` isn't just `{lock,partial,auxfiles}`) before allowing search — a fresh proot-distro image likely also ships without populated lists; verify and gate the same way.
- Curated fallback package list shown before any search is typed (XLabs' `CURATED_PACKAGES`, ~30 entries) — reasonable default UX to keep.
- **Parameterize per-container** instead of XLabs' single hardcoded container name — every function takes a `container: str` argument.

### 5. `screens/box_manager.py`
Table view: name, image ref, size, created date (from `proot-distro list`/manifest.json). Actions: create, enter, remove, rename, backup, restore — each destructive action behind Phase 1's `ConfirmScreen`. "Enter" drops into an interactive shell (not the TUI — hand off the terminal, matching how `proot-distro login` and dextop's `container-session -u` both work today).

## Testing

- Create/enter/remove roundtrip on **2+ different images** (e.g. `debian:13`, `ubuntu:24.04`) to confirm the wrapper isn't accidentally Debian-specific.
- User creation test: from inside the container, touch a file; from the host (`ls -l` on the container's rootfs path), confirm the file's owning UID matches the real host UID — this is the actual pass/fail signal for "host-UID-mapped" working, not just "user creation didn't error."
- Package install/search against a real curated package end-to-end.
- DNS: confirm `apt update` succeeds immediately after `dexpro box create` without a manual Doctor DNS fix first.

## Exit criteria

`dexpro box create work ubuntu:24.04 && dexpro box user add work && dexpro box enter work` results in a working shell as a non-root, host-UID-mapped user, DNS already functional, with zero manual intervention.
