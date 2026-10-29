"""Run the test suite in parallel: each test file in its own process, as many at once as the machine has cores.

    python3 tests/run.py                      # every test file
    python3 tests/run.py -j 4                 # four at a time
    python3 tests/run.py test_autopilot test_gate_rules
    python3 tests/run.py --coverage           # each file under `coverage run -p`; then `coverage combine`

Each file runs as `python -m unittest discover -s tests -p <file>`, the way the whole suite runs, so a file sees the same
set-up as under `discover`; a process per file keeps the globals, the working directory, and the environment one test
patches away from every other file. It uses only the standard library. The suite in one process,
`python3 -m unittest discover -s tests`, stays the reference: this runner only spreads the same files over cores.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent


@dataclass
class Result:
    name: str
    code: int
    seconds: float
    ran: int
    skipped: int
    output: str

    @property
    def passed(self) -> bool:
        """A file passes when its process exits 0 and it ran at least one test. Python 3.11's unittest exits 0 when it
        collects no tests (3.12 and later exit 5), so the count is checked too: a file that runs nothing proves nothing."""
        return self.code == 0 and self.ran > 0


def counts(stderr: str) -> tuple[int, int]:
    """(tests run, tests skipped) from unittest's summary. The runner writes it to stderr after every test, so the last
    `Ran N tests` line there is the summary, never a line a test printed; no summary reads as 0 tests run. Python 3.14
    colors the summary under FORCE_COLOR or PYTHON_COLORS, so the color codes go first."""
    stderr = re.sub(r"\x1b\[[0-9;]*m", "", stderr)
    ran = re.findall(r"^Ran (\d+) tests?", stderr, re.M)
    skipped = re.findall(r"^(?:OK|FAILED) \(.*?\bskipped=(\d+)", stderr, re.M)
    return (int(ran[-1]) if ran else 0, int(skipped[-1]) if skipped else 0)


# How long each file took on its last run here, so the next run starts the slowest first. In __pycache__, which git
# ignores: a fresh checkout has none, and orders by size instead.
DURATIONS = TESTS / "__pycache__" / "run-durations.json"


def last_durations() -> dict[str, float]:
    """Each file's seconds on its last run here; {} when there is no record or it does not read."""
    try:
        data = json.loads(DURATIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: float(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, (int, float))} if isinstance(data, dict) else {}


def keep_durations(results: list[Result]) -> None:
    """Record each file's seconds for the next run's order. Only the order depends on it, so a write that fails is
    skipped."""
    data = last_durations() | {r.name: round(r.seconds, 1) for r in results}
    try:
        DURATIONS.parent.mkdir(exist_ok=True)
        DURATIONS.write_text(json.dumps(data, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def files(names: list[str]) -> list[Path]:
    """The test files to run: those named (with or without `test_` and `.py`), else every `test_*.py`. Slowest first,
    so the slow files start early and the run ends sooner: by each file's time on the last run here (DURATIONS), and a
    file with no time yet, such as every file on a fresh checkout, by its size, ahead of the rest."""
    every = sorted(TESTS.glob("test_*.py"))
    if names:
        wanted = {n.removesuffix(".py") if n.startswith("test_") else f"test_{n.removesuffix('.py')}" for n in names}
        missing = wanted - {p.stem for p in every}
        if missing:
            raise SystemExit(f"no such test file: {', '.join(sorted(missing))}")
        every = [p for p in every if p.stem in wanted]
    last = last_durations()
    return sorted(every, key=lambda p: (p.stem not in last, last.get(p.stem, 0.0), p.stat().st_size), reverse=True)


def run_one(path: Path, coverage: bool) -> Result:
    head = [sys.executable, "-m", "coverage", "run", "-p", "--branch", "--source=src/aidd,plugins/aidd-team/tools"] if coverage else [sys.executable]
    cmd = [*head, "-m", "unittest", "discover", "-s", "tests", "-p", path.name]
    start = time.monotonic()
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    ran, skipped = counts(done.stderr)
    output = done.stdout + done.stderr
    if ran == 0 and done.returncode == 0:
        output += f"\n{path.name} ran no tests: a file that runs nothing fails, so check its imports and test names.\n"
    return Result(path.stem, done.returncode, time.monotonic() - start, ran, skipped, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the test files in parallel, one process each.")
    parser.add_argument("names", nargs="*", metavar="FILE", help="test files to run, such as test_autopilot (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2, help="files at once (default: the number of cores)")
    parser.add_argument("--coverage", action="store_true", help="run each file under `coverage run -p`; combine with `coverage combine`")
    parser.add_argument("--slowest", type=int, default=10, metavar="N", help="list the N slowest files at the end (default 10)")
    args = parser.parse_args(argv)

    todo = files(args.names)
    start = time.monotonic()
    results: list[Result] = []
    # Threads only wait: each file runs in its own process. Each line prints as its file finishes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        running = [pool.submit(run_one, path, args.coverage) for path in todo]
        for future in concurrent.futures.as_completed(running):
            result = future.result()
            results.append(result)
            mark = "ok  " if result.passed else "FAIL"
            print(f"{mark} {result.name} ({result.ran} tests, {result.seconds:.1f}s)", flush=True)
    wall = time.monotonic() - start
    keep_durations(results)

    failed = [r for r in results if not r.passed]
    for r in failed:
        print(f"\n{'=' * 70}\n{r.name}\n{'=' * 70}\n{r.output.rstrip()}")
    print(f"\nThe slowest {min(args.slowest, len(results))} files:")
    for r in sorted(results, key=lambda r: r.seconds, reverse=True)[: args.slowest]:
        print(f"  {r.seconds:6.1f}s  {r.name} ({r.ran} tests)")
    ran, skipped = sum(r.ran for r in results), sum(r.skipped for r in results)
    print(f"\nRan {ran} tests in {len(results)} files in {wall:.1f}s, {args.jobs} at a time")
    if failed:
        print(f"FAILED: {', '.join(r.name for r in failed)}")
        return 1
    print(f"OK (skipped={skipped})" if skipped else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
