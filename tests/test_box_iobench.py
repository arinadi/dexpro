"""app/box/iobench.py: fio JSON score parsing, and graceful behavior
when proot-distro/fio aren't available.

    python tests/test_box_iobench.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support import check, run

from app.box import iobench

_SAMPLE_FIO_JSON = """\
{
  "jobs": [
    {"jobname": "randrw4k", "read": {"iops": 100.5}, "write": {"iops": 50.5}},
    {"jobname": "filecreate", "read": {"iops": 0}, "write": {"iops": 200.0}}
  ]
}
"""


def test_parse_score_sums_read_and_write_iops_across_jobs() -> None:
    score = iobench._parse_score(_SAMPLE_FIO_JSON)
    check(score == 351.0, f"expected 100.5+50.5+0+200.0=351.0, got {score!r}")


def test_parse_score_skips_leading_warning_lines() -> None:
    # fio sometimes prints a warning before the JSON blob (a missing
    # tunable, a libaio fallback notice) — the parser must slice from
    # the first "{" rather than fail the whole parse over it.
    noisy = "fio: some warning about io_uring\n" + _SAMPLE_FIO_JSON
    check(iobench._parse_score(noisy) == 351.0, "should still parse past the warning line")


def test_parse_score_none_for_garbage() -> None:
    check(iobench._parse_score("not json at all") is None, "garbage input must not raise")
    check(iobench._parse_score("") is None, "empty input must not raise")


def test_parse_score_none_when_no_jobs() -> None:
    check(iobench._parse_score('{"jobs": []}') is None, "no jobs means no score, not zero")


def test_fio_installed_fails_gracefully_when_proot_distro_missing() -> None:
    result = iobench.fio_installed("definitely-not-a-real-container")
    check(result is False, "should report False, not raise, when proot-distro is unavailable")


def test_run_fails_gracefully_when_proot_distro_missing() -> None:
    messages: list[str] = []
    # Must not raise even though installing fio and every subsequent
    # measurement will fail on this dev machine.
    iobench.run("definitely-not-a-real-container", log=messages.append)
    check(messages, "should have logged something explaining the failure")


TESTS = [
    test_parse_score_sums_read_and_write_iops_across_jobs,
    test_parse_score_skips_leading_warning_lines,
    test_parse_score_none_for_garbage,
    test_parse_score_none_when_no_jobs,
    test_fio_installed_fails_gracefully_when_proot_distro_missing,
    test_run_fails_gracefully_when_proot_distro_missing,
]

if __name__ == "__main__":
    sys.exit(run(TESTS, label=os.path.basename(__file__)))
