"""Which proot-distro login flags a given dexpro-box container's
sessions use — ported from XLabs' isolation.py.

--isolated skips mounting /sdcard and the Termux $HOME, meaning fewer
bind-mount entries for proot's ptrace layer to resolve on every open/
stat/read syscall a container process makes. Whether that trade is
actually faster depends on the device and the container's own
workload, so it's measured (iobench.py) rather than assumed — the same
"measure, don't guess" reasoning native/gpu.py already uses for GPU
renderer selection.

Proot-only, box-only: the native session has zero proot involvement by
design (see native/audio.py's own docstring on the same point) — this
entire module only means anything for dexpro-box containers, never the
native layer.

Per-container, not global like XLabs' single-container version:
dexpro-box supports N containers, each potentially benefiting from a
different preset depending on what it's used for.
"""

from __future__ import annotations

import os
from typing import NamedTuple

from .. import config

# termux-setup-storage's symlink target — the usual way in to phone
# storage once --isolated has stopped binding it automatically.
STORAGE_BIND = os.path.expanduser("~/storage/shared")


class Preset(NamedTuple):
    name: str
    description: str
    flags: tuple[str, ...]  # extra proot-distro login flags beyond --shared-tmp


PRESETS: tuple[Preset, ...] = (
    Preset("default", "Full Android/host access (default)", ()),
    Preset("isolated", "Isolated — skip Android bindings", ("--isolated",)),
    Preset(
        "isolated-storage",
        "Isolated + /mnt/android storage",
        ("--isolated", "--bind", f"{STORAGE_BIND}:/mnt/android"),
    ),
)

DEFAULT_PRESET = PRESETS[0]


def preset_by_name(name: str) -> Preset | None:
    return next((p for p in PRESETS if p.name == name), None)


def _key(container: str) -> str:
    return f"PROOT_ISOLATION__{container}"


def _score_key(container: str) -> str:
    return f"PROOT_ISOLATION_SCORE__{container}"


def load_preset(container: str) -> Preset:
    """The configuration a previous iobench run chose for this
    container, or the safe (full-access) default."""
    name = config.get(_key(container))
    return (preset_by_name(name) if name else None) or DEFAULT_PRESET


def save_preset(container: str, preset: Preset, score: float) -> None:
    config.set_value(_key(container), preset.name)
    config.set_value(_score_key(container), str(score))


def set_preset_manually(container: str, preset: Preset) -> None:
    """A manual override rather than a measured result — clears the
    score, which would otherwise misreport this pick as benchmarked."""
    config.set_value(_key(container), preset.name)
    config.unset(_score_key(container))
