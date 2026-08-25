"""Measure which proot isolation preset (isolation.py) is fastest for a
given dexpro-box container, then keep it — ported from XLabs' iobench.py,
adapted to run per-container instead of against one fixed container.

--isolated trades away /sdcard and Termux $HOME access for fewer bind-
mount entries proot's ptrace layer has to resolve on every syscall.
Whether that trade pays off depends on how many binds the container
would otherwise carry and how syscall-heavy its actual workload is —
unknown ahead of time, so this measures it with fio rather than
assuming, the same way native/gpu.py measures GPU presets instead of
guessing from hardware guidance.

The workload targets the container's own home directory, not a shared-
tmp path: a path bound straight through from Termux would score
identically under every preset and prove nothing about the binds
actually being varied. fio's filecreate/filestat/filedelete engines
mimic the metadata-heavy pattern (`npm install`, codebase-wide search)
that proot's ptrace overhead hits hardest; a small-file randrw job
covers ordinary read/write on top of that.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

from . import isolation, packages
from . import manager as box_manager

Log = Callable[[str], None]

WORK_DIR = "/root/.cache/dexpro-iobench"
JOB_PATH = "/root/.dexpro-iobench.fio"

# Short enough that testing three presets back to back stays under a
# minute; long enough that a cold cache doesn't dominate the number.
RUNTIME_SECONDS = 2
NRFILES = 150

JOB_FILE = f"""[global]
directory={WORK_DIR}
group_reporting=1

[randrw4k]
stonewall
rw=randrw
bs=4k
size=4m
ioengine=sync
runtime={RUNTIME_SECONDS}
time_based=1

[filecreate]
stonewall
ioengine=filecreate
nrfiles={NRFILES}
filesize=4k

[filestat]
stonewall
ioengine=filestat
nrfiles={NRFILES}

[filedelete]
stonewall
ioengine=filedelete
nrfiles={NRFILES}
"""

BENCH_SCRIPT = (
    f"mkdir -p {WORK_DIR} && "
    f"cat > {JOB_PATH} << 'DEXPRO_EOF'\n{JOB_FILE}DEXPRO_EOF\n"
    f"fio --output-format=json {JOB_PATH}; rc=$?; rm -rf {WORK_DIR} {JOB_PATH}; exit $rc"
)

# A preset has to beat the default by more than noise before it's worth
# the /sdcard and $HOME access it costs — otherwise "isolated" would win
# on measurement jitter alone and nobody would notice the trade until
# they went looking for a file that used to just be there.
WORTHWHILE_MARGIN = 1.05


def _parse_score(output: str) -> float | None:
    """Total IOPS across every job's read and write phase. fio
    sometimes prints a warning line or two before the JSON blob (a
    missing tunable, a libaio fallback notice); slicing from the first
    "{" skips those rather than failing the whole parse over cosmetic
    noise."""
    start = output.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(output[start:])
    except (ValueError, json.JSONDecodeError):
        return None

    jobs = data.get("jobs", [])
    if not jobs:
        return None

    total = 0.0
    for job in jobs:
        for direction in ("read", "write"):
            total += job.get(direction, {}).get("iops", 0.0)
    return total if total > 0 else None


def fio_installed(container: str) -> bool:
    full = box_manager.login_command(container, ["sh", "-c", "command -v fio"])
    try:
        result = subprocess.run(full, capture_output=True, timeout=15)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _measure(container: str, preset: isolation.Preset, log: Log | None = None) -> float | None:
    full = box_manager.login_command(
        container, ["sh", "-c", BENCH_SCRIPT], isolation_preset=preset
    )
    timeout = RUNTIME_SECONDS * 5 + 30
    try:
        result = subprocess.run(full, capture_output=True, timeout=timeout, text=True)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        if log:
            log(f"    {preset.name}: {exc}")
        return None
    return _parse_score(result.stdout)


def run(container: str, log: Log) -> None:
    """Benchmark each isolation preset for `container` and keep the
    winner, if it's worth it."""
    if not fio_installed(container):
        log("fio is not in the container, installing it...")
        if not packages.install(container, ["fio"], log=log):
            log("[red]Could not install fio.[/red]")
            return
        log("")

    results: list[tuple[isolation.Preset, float | None]] = []
    for preset in isolation.PRESETS:
        log(f"── {preset.name}: {preset.description}")
        score = _measure(container, preset, log=log)
        if score is None:
            log("    no score")
        else:
            log(f"    {score:.0f} combined IOPS")
        results.append((preset, score))
        log("")

    log("── Results ───────────────────────────────────")
    for preset, score in results:
        log(f"  {preset.name:<18} {'failed' if score is None else f'{score:.0f}'}")
    log("")

    scored = [(p, s) for p, s in results if s is not None]
    if not scored:
        log("[red]Nothing produced a score.[/red]")
        return

    scores = dict(scored)
    best, best_score = max(scored, key=lambda pair: pair[1])
    baseline = scores.get(isolation.DEFAULT_PRESET)

    log(f"[bold green]Best: {best.name} ({best_score:.0f} IOPS)[/bold green]")

    if best is isolation.DEFAULT_PRESET or baseline is None:
        keep, keep_score = isolation.DEFAULT_PRESET, baseline or best_score
    elif best_score >= baseline * WORTHWHILE_MARGIN:
        keep, keep_score = best, best_score
        log(f"  {best_score / baseline:.2f}x the default preset — worth the trade")
    else:
        keep, keep_score = isolation.DEFAULT_PRESET, baseline
        log("  within noise of the default — keeping full Android/host access")

    isolation.save_preset(container, keep, keep_score)
    log(f"  saved for '{container}' — Enter and every other session use it from now on")
