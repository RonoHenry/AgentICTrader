#!/usr/bin/env python
"""Run every AgentICTrader test suite and exit nonzero if any of them fails.

The repository has two independent pytest configurations:

  root     ./pytest.ini           tests/, ml/, agent/, services/, nlp/, scripts/rag/tests/
  backend  ./backend/pytest.ini   backend/tests/  (Django: agentictrader.settings_test)

They are run as two separate pytest processes, one after the other, and the
results are aggregated into a single exit code. A single pytest process
cannot safely collect both:

  * Both ``tests/`` and ``backend/tests/`` are top-level packages named
    ``tests``. Whichever is imported first wins ``sys.modules["tests"]``;
    ``backend/conftest.py`` then fails on ``tests.infrastructure``.
  * The two suites configure Django differently (``backend.agentictrader.settings``
    from ``tests/conftest.py`` vs ``agentictrader.settings_test`` from
    ``backend/pytest.ini``, plus ``backend/conftest.py`` rewriting
    ``INSTALLED_APPS``/``DATABASES``). Django can only be set up once per process.
  * Many backend test modules push the repo root, ``backend/``, ``scripts/``
    and individual ``services/*`` directories onto ``sys.path[0]`` at import
    time, which would change what bare imports resolve to in the root suite.

Usage (from anywhere; paths are resolved relative to the repo):

  python scripts/run_all_tests.py                    # every suite, live tests deselected
  python scripts/run_all_tests.py --live             # also run tests marked infrastructure
  python scripts/run_all_tests.py --suite backend    # one suite only (repeatable)
  python scripts/run_all_tests.py -- -x -k risk      # args after -- go to every pytest run
  python scripts/run_all_tests.py --dry-run          # print the commands, run nothing

Live tests: both pytest.ini files deselect tests marked ``infrastructure`` by
default (``-m "not infrastructure"``) because they need Docker services,
InfluxDB, Qdrant, an MLflow server or a live broker/data feed. ``--live`` passes
``-m ""``, which clears that filter. Your own ``-m EXPR`` after ``--`` wins over both.

Exit code: 0 when every suite passed (a suite that selects no tests, pytest
exit code 5, counts as passing). Otherwise the highest pytest exit code seen:
1 = tests failed or modules failed to import, 2 = interrupted, 3 = internal
error, 4 = usage error.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# pytest exit codes (pytest.ExitCode)
EXIT_OK = 0
EXIT_NO_TESTS_COLLECTED = 5


@dataclass(frozen=True)
class Suite:
    name: str
    cwd: Path
    description: str


SUITES: dict[str, Suite] = {
    "root": Suite(
        name="root",
        cwd=REPO_ROOT,
        description="./pytest.ini - tests/ ml/ agent/ services/ nlp/ scripts/rag/tests/",
    ),
    "backend": Suite(
        name="backend",
        cwd=REPO_ROOT / "backend",
        description="backend/pytest.ini - backend/tests/ (Django)",
    ),
}


@dataclass
class SuiteResult:
    suite: Suite
    exit_code: int
    duration: float
    counts: dict[str, int] | None = field(default=None)


def default_python() -> str:
    """Interpreter for the pytest subprocesses.

    The interpreter running this script, when it is a virtualenv. Otherwise the
    repo's ``.venv`` if one exists (so ``python scripts/run_all_tests.py`` with a
    bare system Python still picks up the project's dependencies).
    """
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        return sys.executable
    for candidate in (
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    if "--" in argv:
        split = argv.index("--")
        own, passthrough = argv[:split], argv[split + 1 :]
    else:
        own, passthrough = argv, []

    parser = argparse.ArgumentParser(
        description="Run the root and backend pytest suites as separate processes "
        "and exit nonzero if any test fails. Arguments after -- are passed to "
        "every pytest invocation.",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITES),
        help="run only this suite (repeatable; default: all suites)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help='include tests marked infrastructure (passes -m ""); they need '
        "Docker services, InfluxDB, Qdrant, an MLflow server or a live data feed",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="interpreter for the pytest subprocesses (default: the active venv, "
        "else ./.venv)",
    )
    parser.add_argument(
        "--junit-dir",
        default=None,
        help="keep each suite's JUnit XML report in this directory "
        "(default: a temporary directory that is deleted afterwards)",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="do not start the next suite once one has failed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the pytest commands without running them",
    )
    return parser.parse_args(own), passthrough


def build_command(
    python: str, junit_xml: Path, live: bool, passthrough: list[str]
) -> list[str]:
    cmd = [
        python,
        "-m",
        "pytest",
        # A module that fails to import is reported as an error (and makes the
        # exit code nonzero) instead of aborting the whole suite before any
        # test runs.
        "--continue-on-collection-errors",
        f"--junitxml={junit_xml}",
    ]
    if live:
        # An empty mark expression disables the ini's default "-m not ..." filter.
        cmd += ["-m", ""]
    return cmd + passthrough


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    # Each suite picks its own Django settings (backend/pytest.ini, or the
    # setdefault in tests/conftest.py). pytest-django lets an exported
    # DJANGO_SETTINGS_MODULE override the ini, so a stray value in the shell
    # (the old run_tests scripts exported one) would silently change results.
    env.pop("DJANGO_SETTINGS_MODULE", None)
    # Test output contains non-ASCII text; without this, a child whose stdout
    # is a pipe on Windows encodes with cp1252 and can crash while reporting.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def read_counts(junit_xml: Path) -> dict[str, int] | None:
    """passed/failed/errors/skipped/total from a pytest JUnit XML report."""
    try:
        root = ET.parse(junit_xml).getroot()
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for ts in suites:
        for key in totals:
            totals[key] += int(ts.get(key, 0) or 0)
    return {
        "passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"],
        "failed": totals["failures"],
        "errors": totals["errors"],
        "skipped": totals["skipped"],
        "total": totals["tests"],
    }


def run_suite(
    suite: Suite, python: str, junit_dir: Path, live: bool, passthrough: list[str]
) -> SuiteResult:
    junit_xml = junit_dir / f"{suite.name}.xml"
    if junit_xml.exists():
        junit_xml.unlink()
    cmd = build_command(python, junit_xml, live, passthrough)
    banner(f"suite: {suite.name}  ({suite.description})")
    print(f"cwd: {suite.cwd}")
    print("cmd: " + subprocess.list2cmdline(cmd), flush=True)
    start = time.monotonic()
    # stdout/stderr are inherited so pytest drives the terminal directly
    # (colours, progress, -s output) exactly as when run by hand.
    proc = subprocess.run(cmd, cwd=suite.cwd, env=child_env())
    duration = time.monotonic() - start
    return SuiteResult(suite, proc.returncode, duration, read_counts(junit_xml))


def banner(text: str) -> None:
    width = max(72, len(text) + 4)
    print("\n" + "#" * width, flush=True)
    print(f"# {text}", flush=True)
    print("#" * width, flush=True)


def suite_passed(result: SuiteResult) -> bool:
    return result.exit_code in (EXIT_OK, EXIT_NO_TESTS_COLLECTED)


def print_summary(results: list[SuiteResult], not_run: list[Suite]) -> None:
    banner("summary")
    header = f"{'suite':<10}{'result':<8}{'exit':>5}{'passed':>8}{'failed':>8}{'errors':>8}{'skipped':>9}{'time':>9}"
    print(header)
    print("-" * len(header))
    for r in results:
        status = "PASS" if suite_passed(r) else "FAIL"
        if r.counts is None:
            nums = f"{'?':>8}{'?':>8}{'?':>8}{'?':>9}"
        else:
            c = r.counts
            nums = f"{c['passed']:>8}{c['failed']:>8}{c['errors']:>8}{c['skipped']:>9}"
        print(f"{r.suite.name:<10}{status:<8}{r.exit_code:>5}{nums}{r.duration:>8.0f}s")
    for s in not_run:
        print(f"{s.name:<10}{'SKIP':<8}{'-':>5}   (not run: an earlier suite failed and --stop-on-failure is set)")
    if any(r.exit_code == EXIT_NO_TESTS_COLLECTED for r in results):
        print("\nnote: exit 5 = no tests selected in that suite (counted as passing).")
    print(
        "\nerrors = tests that errored in setup/teardown plus test modules that "
        "failed to import (see each suite's 'short test summary info' above)."
    )


def overall_exit_code(results: list[SuiteResult]) -> int:
    failing = [r.exit_code for r in results if not suite_passed(r)]
    return max(failing) if failing else EXIT_OK


def main(argv: list[str]) -> int:
    args, passthrough = parse_args(argv)
    python = args.python or default_python()
    selected = [SUITES[name] for name in (args.suite or SUITES)]
    # Keep the order stable (root, backend) and drop duplicate --suite values.
    selected = [s for s in SUITES.values() if s in selected]

    print(f"python: {python}")
    if "DJANGO_SETTINGS_MODULE" in os.environ:
        print(
            "note: ignoring DJANGO_SETTINGS_MODULE from the environment; each "
            "suite uses its own pytest.ini/conftest settings."
        )
    if args.live:
        print('live mode: infrastructure tests included (-m "").')

    if args.dry_run:
        for suite in selected:
            cmd = build_command(python, Path(f"<junit-dir>/{suite.name}.xml"), args.live, passthrough)
            print(f"[{suite.name}] (cd {suite.cwd} && {subprocess.list2cmdline(cmd)})")
        return EXIT_OK

    tmp_dir = None
    if args.junit_dir:
        junit_dir = Path(args.junit_dir).resolve()
        junit_dir.mkdir(parents=True, exist_ok=True)
    else:
        tmp_dir = tempfile.mkdtemp(prefix="agentictrader-tests-")
        junit_dir = Path(tmp_dir)

    results: list[SuiteResult] = []
    not_run: list[Suite] = []
    try:
        for i, suite in enumerate(selected):
            result = run_suite(suite, python, junit_dir, args.live, passthrough)
            results.append(result)
            if args.stop_on_failure and not suite_passed(result):
                not_run = selected[i + 1 :]
                break
    except KeyboardInterrupt:
        print("\ninterrupted", flush=True)
        if results:
            print_summary(results, [])
        return 2
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    print_summary(results, not_run)
    code = overall_exit_code(results)
    print(f"\noverall: {'PASS' if code == EXIT_OK else 'FAIL'} (exit {code})")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
