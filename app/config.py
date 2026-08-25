"""Per-device settings — plain KEY=value at const.CONFIG_FILE.

Ported from XLabs' installer/config.py near-verbatim (build-task-phase1.md
Task 1): no schema, everything is a string, values are quote-stripped on
read and rewritten sorted-by-key with a header comment.
"""

from __future__ import annotations

import os

from . import const


def _read_lines() -> list[str]:
    if not os.path.exists(const.CONFIG_FILE):
        return []
    with open(const.CONFIG_FILE, encoding="utf-8") as f:
        return f.readlines()


def load() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in _read_lines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def get(key: str, default: str | None = None) -> str | None:
    return load().get(key, default)


def set_value(key: str, value: str) -> None:
    values = load()
    values[key] = value
    _write(values)


def unset(key: str) -> None:
    values = load()
    if key in values:
        del values[key]
        _write(values)


def _write(values: dict[str, str]) -> None:
    directory = os.path.dirname(const.CONFIG_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    lines = ["# dexpro per-device settings — KEY=value, one per line\n"]
    for key in sorted(values):
        lines.append(f"{key}={values[key]}\n")
    with open(const.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
