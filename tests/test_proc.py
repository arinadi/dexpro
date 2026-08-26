"""app/native/proc.py: shared kill-verify-escalate helper, without a
real pgrep/pkill on this dev machine.

    python tests/test_proc.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.native import proc


def test_pgrep_returns_false_gracefully_when_absent() -> None:
    # No pgrep on this Windows dev machine — must fail gracefully to
    # False, not raise.
    check(proc.pgrep("anything") is False, "expected False when pgrep is unavailable")


def test_kill_pattern_is_a_noop_when_nothing_matches() -> None:
    # pgrep is unavailable here, so pgrep() always reports False — the
    # pattern is "already gone" from kill_pattern()'s point of view.
    check(proc.kill_pattern("nonexistent-process-xyz") is True, "should report already gone")


def test_kill_pattern_escalates_to_sigkill_when_term_does_not_work() -> None:
    # Regression test for a real reported bug: "polite kill" (TERM only)
    # wasn't actually working. Simulates a process that survives TERM
    # but is gone after KILL.
    from unittest import mock

    pgrep_results = iter([True, True, False])  # initial, post-TERM-wait, post-KILL
    run_calls = []

    def fake_pgrep(pattern):
        return next(pgrep_results, False)

    def fake_run(cmd, **kwargs):
        run_calls.append(cmd)
        import subprocess

        return subprocess.CompletedProcess(cmd, 0)

    messages: list[str] = []
    with mock.patch.object(proc, "pgrep", side_effect=fake_pgrep):
        with mock.patch.object(proc, "time") as fake_time:
            fake_time.monotonic.side_effect = [0, 100]  # deadline expires immediately
            with mock.patch.object(proc.subprocess, "run", side_effect=fake_run):
                result = proc.kill_pattern("stubborn-process", log=messages.append, wait=3.0)
    check(result is True, "must report success once KILL finishes it off")
    check(["pkill", "-TERM", "-f", "stubborn-process"] in run_calls, f"got {run_calls!r}")
    check(["pkill", "-9", "-f", "stubborn-process"] in run_calls, f"got {run_calls!r}")
    check(any("sending KILL" in m for m in messages), f"expected escalation logged: {messages!r}")


def test_kill_pattern_reports_failure_if_sigkill_also_does_not_work() -> None:
    from unittest import mock

    messages: list[str] = []
    with mock.patch.object(proc, "pgrep", return_value=True):
        with mock.patch.object(proc, "time") as fake_time:
            fake_time.monotonic.side_effect = [0, 100]
            with mock.patch.object(proc.subprocess, "run", return_value=None):
                result = proc.kill_pattern("unkillable", log=messages.append, wait=1.0)
    check(result is False, "must report failure when even SIGKILL didn't clear it")
    check(any("survived even SIGKILL" in m for m in messages), f"got {messages!r}")


TESTS = [
    test_pgrep_returns_false_gracefully_when_absent,
    test_kill_pattern_is_a_noop_when_nothing_matches,
    test_kill_pattern_escalates_to_sigkill_when_term_does_not_work,
    test_kill_pattern_reports_failure_if_sigkill_also_does_not_work,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
