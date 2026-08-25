# Build Task — Phase 5: Android Integration Polish

Status: Draft v1
Date: 2026-08-25
Depends on: Phase 1 (native layer), Phase 2 (box/packages.py)
PRD refs: G5, §5.3, §6

## Objective

Storage auto-linking, mimetype/activity bridging to native Android apps, Settings, and Store UX — the dextop-and-XLabs feature areas that round out day-to-day usability, ported with corrections rather than copied as-is.

## Proposed module layout (adds to `app/`)

```
app/
├── android/
│   ├── storage.py    # Task 1
│   └── bridge.py      # Task 2
└── screens/
    ├── settings.py    # Task 3
    └── store.py        # Task 4
```

## Tasks

### 1. `android/storage.py`
Port dextop's `termux-storage` logic:
- Storage-permission trigger, exact invocation confirmed from source: `am broadcast --user 0 -e com.termux.app.reload_style storage -a com.termux.app.reload_style com.termux`, fired if `~/.dextop`-equivalent marker file is absent and `~/storage` doesn't exist yet.
- Primary storage: if `/storage/self/primary` exists, link it under a `media/` directory (dextop's `frobulator.link` call — reimplement as a plain Python symlink helper).
- External storage: parse `/proc/mounts`, match lines under `/storage` against a volume-ID pattern. **Caution**: the research report's regex (`[A0-Z9]{4}-[A0-Z9]{4}` / `[A0-Z9]{40}`) reads as a garbled character class — **re-verify the exact pattern directly from `termux-storage`'s source before implementing**, don't port a possibly-mistyped regex blind. The intent is clear (short FAT-style volume ID like `XXXX-XXXX` hex, or a long UUID), the exact character class needs a source re-check.
- `.storage` label-file convention at each mount root (read if present; fall back to the UUID/volume ID with a warning if absent).
- `-l/--link` unified-home mechanism: find a case-insensitive `Home`-labeled mount under the media dir, symlink each top-level entry into the actual home directory (replacing existing dirs) — port as an explicit opt-in flag, matching dextop's own default-off behavior for this specific mode.
- Default (no `-l`): ensure standard subfolders exist directly under home (Desktop/Documents/Downloads/Music/Pictures/Public/Templates/Videos).

### 2. `android/bridge.py`
Port dextop's `dextop-additions` **concept**, not its code — two confirmed bugs must not be carried forward:

1. **Fix the broken multi-condition matcher.** dextop's shell `[[ ]] || [[ ]] [[ ]]` chains for synonym matching (e.g. photo/picture/selfie-type activity names) only actually OR the first pair — later conditions in the chain aren't properly joined, so several documented synonyms silently never match. Implement as a proper Python dict/list-based lookup instead of porting the shell conditional structure.
2. **Do not port the hostname-heredoc bug** (irrelevant here — that was in `termux-system`'s container `/etc` scaffolding, not `dextop-additions`, but noted as a general "don't port bugs, port intent" reminder for this whole file).

What's sound and worth keeping from dextop's design:
- **Generic scheme-based intent handoff** for mimetype/activity bridging: `am start --user 0 -a android.intent.action.VIEW -d "<scheme>:..."` — email→`mailto:`, browser/link/web→`https:`, message/text/sms→`sms:`, file→`file:`. This hands off to Android's own default-app resolution rather than dextop's separate hardcoded activity-component list (chrome/gmail/terminal component names, which are brittle against app updates/replacements) — prefer the scheme-based path as the primary mechanism, treat the hardcoded-component path as a narrow fallback if at all.
- Do not port the ~450 commented-out lines of Android intent constants as live code — keep as an external reference doc/comment at most, not part of the shipped module.

### 3. `screens/settings.py`
Port XLabs' `config.py` `KEY=value` `.env` pattern directly — proven, simple, no schema needed. Exposed settings:
- GPU profile override (bypass Phase 1's bench result)
- Audio method override
- WM choice (XFCE vs whatever Phase 1's spike settled on)
- Storage link toggle (`-l` mode from Task 1)
- `termux-x11` diagnostic flags for known-broken devices (`-legacy-drawing`, `-force-bgra`, per Phase 1)

Uninstall action lives here, behind the same `ConfirmScreen` as any other destructive action — matches XLabs' placement convention (Settings screen, not buried in Main menu).

### 4. `screens/store.py`
Port XLabs' `packages.py` Store UX closely — it's the most fully-designed piece of prior art across both reference projects:
- Curated package list (XLabs' `CURATED_PACKAGES`, ~30 entries) shown before any search is typed.
- Mirror measurement: parse the **deb822 masterlist** (`http://mirror-master.debian.org/status/Mirrors.masterlist`), not the HTML mirror page — measure real download speed via `curl -w "%{speed_download}"` against `<mirror>/dists/trixie/Release`, not ICMP ping.
- `security.debian.org` always pinned regardless of chosen mirror — identified by parsing the `Suites:` deb822 field, not by matching on URI content.
- Custom repo add: requires an explicit signing key URL (never trust a third-party repo via Debian's own keyring), validated via the `SAFE_URI`/`SAFE_WORDS` regex gates XLabs already uses.
- **This screen sits on top of Phase 2's `box/packages.py`** — same UX, now with a container selector, since v1's model is N containers rather than XLabs' single fixed one.

### 5. Doctor additions (feeds back into Phase 4)
- Storage link health (are the expected symlinks present and pointing at live mounts?).
- Mimetype bridge sanity — does a scheme handoff (`mailto:`/`https:`/etc.) actually resolve to an installed app, or silently no-op?

## Testing

- Plug in an external SD card (or simulate via a labeled loopback mount if hardware isn't available for a given test pass), confirm auto-link appears under the configured label.
- Trigger a `mailto:`/`https:`/`sms:` handoff from inside a container app, confirm it opens the correct native Android app (not a dead intent).
- Change a Settings value, restart the native session (Phase 1), confirm the new value actually takes effect — not just persisted to `.env` without being read.
- Mirror measurement: confirm the fastest-measured mirror is actually used for subsequent `apt` operations, and that `security.debian.org` stays pinned after a mirror switch.

## Exit criteria

Storage, Settings, Store, and Android-app bridging are all functional across the native layer and `dexpro-box` containers, matching or exceeding XLabs' and dextop's combined feature set in these specific areas — without carrying forward either project's known bugs (dextop's synonym-matcher, XLabs' none identified in this area).
