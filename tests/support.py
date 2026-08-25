"""Shared helpers for the split-out test modules.

Ported near-verbatim from XLabs' tests/support.py.
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable, Sequence


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def wait_for_rows(pilot, app, selector: str, attempts: int = 80) -> int:
    from textual.widgets import DataTable

    for _ in range(attempts):
        await asyncio.sleep(0.1)
        await pilot.pause()
        rows = app.screen.query_one(selector, DataTable).row_count
        if rows:
            return rows
    return app.screen.query_one(selector, DataTable).row_count


def run(tests: Sequence[Callable], label: str = "") -> int:
    """Run `tests` in order, printing ok/FAIL per test.

    Shared by run_tests.py (the full suite) and each test module's own
    __main__ block (just its own tests, for a fast loop while working on
    one area) — both need the same pass/fail bookkeeping and exit code.
    """
    failures: list[str] = []
    for test in tests:
        name = test.__name__
        try:
            if asyncio.iscoroutinefunction(test):
                asyncio.run(test())
            else:
                test()
        except Exception:
            failures.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
        else:
            print(f"ok    {name}")

    print()
    if failures:
        print(f"{len(failures)} of {len(tests)} failed: {', '.join(failures)}")
        return 1
    suffix = f" ({label})" if label else ""
    print(f"all {len(tests)} passed{suffix}")
    return 0
