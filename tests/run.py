"""Run the test suite in parallel: each test file in its own process, as many at once as the machine has cores.

    python3 tests/run.py                      # every test file
    python3 tests/run.py -j 4                 # four at a time
    python3 tests/run.py test_autopilot test_gate_rules
    python3 tests/run.py --coverage           # each file under `coverage run -p`; then `coverage combine`
    python3 tests/run.py --changed            # only the files that read what changed since the last full run (none: a smoke set)
    python3 tests/run.py --changed --base main   # and what the branch changes since it left main

Each file runs as `python -m unittest discover -s tests -p <file>`, the way the whole suite runs, so a file sees the same
set-up as under `discover`; a process per file keeps the globals, the working directory, and the environment one test
patches away from every other file. It uses only the standard library. The suite in one process,
`python3 -m unittest discover -s tests`, stays the reference: this runner only spreads the same files over cores.

A full run also records which files of the checkout each test file reads (tests/record_reads/sitecustomize.py), and
`--changed` runs a file only when it read a path that changed since, or may read anything. pytest-testmon does the same
from coverage, but it misses every file a child process reads, and these tests start aidd as a child. A full run ends
with the files over FILE_BUDGET_SECONDS and its wall time against WALL_BUDGET_SECONDS: a report, never a failure.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
# The test budget (AGENTS.md, "A feature pays for its own bytes"): the whole suite's wall time, and one file's.
WALL_BUDGET_SECONDS = 120
FILE_BUDGET_SECONDS = 20
# A test file that runs longer than this is hung, not slow: the runner kills its process group and fails the file, so
# one stuck test cannot hang the run. Six times the file budget; the budget report above it stays a report.
FILE_TIMEOUT_SECONDS = 120
# After a file is killed, how long the runner waits for what it printed; a child that left the file's process group may hold the pipe open.
KILL_GRACE_SECONDS = 10
# What `--changed` runs when no test file reads what changed, so an empty selection never passes with nothing run:
# the fast content checks AGENTS.md names before each commit.
SMOKE_FILES = ("plain_language", "knowledge_templates", "team_roles_and_flows", "loop_contract", "code_shape", "doc_currency")


@dataclass
class Result:
    name: str
    code: int
    seconds: float
    ran: int
    skipped: int
    output: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        """A file passes when its process exits 0 and it ran at least one test. Python 3.11's unittest exits 0 when it
        collects no tests (3.12 and later exit 5), so the count is checked too: a file that runs nothing proves nothing.
        A file that timed out never passes."""
        return self.code == 0 and self.ran > 0 and not self.timed_out


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


def run_one(path: Path, coverage: bool, env: dict[str, str] | None = None, folder: str = "tests", timeout: float = FILE_TIMEOUT_SECONDS) -> Result:
    """Run one test file in its own process group. After `timeout` seconds the whole group is killed (the file's tests
    start children of their own), and the file fails as timed out. Git never waits for a password: GIT_TERMINAL_PROMPT=0."""
    env = {**(os.environ if env is None else env), "GIT_TERMINAL_PROMPT": "0", "PYTHONHASHSEED": "0"}  # a hash seed is read at start-up
    head = [sys.executable, "-m", "coverage", "run", "-p", "--branch", "--source=src/aidd,plugins/aidd-team/tools"] if coverage else [sys.executable]
    cmd = [*head, "-m", "unittest", "discover", "-s", folder, "-p", path.name]
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=os.name == "posix",
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:  # it ended between the timeout and the kill
            pass
        try:
            stdout, stderr = proc.communicate(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired as late:  # a child outside the group still holds the output open: take what came
            stdout, stderr = (x.decode("utf-8", "replace") if isinstance(x, bytes) else x or "" for x in (late.stdout, late.stderr))
    ran, skipped = counts(stderr)
    output = stdout + stderr
    if timed_out:
        output += f"\n{path.name} timed out after {timeout:g}s and was killed: a test in it is hung, so find the call that never returns.\n"
    elif ran == 0 and proc.returncode == 0:
        output += f"\n{path.name} ran no tests: a file that runs nothing fails, so check its imports and test names.\n"
    return Result(path.stem, proc.returncode, time.monotonic() - start, ran, skipped, output, timed_out)


# ---- What each test file reads, and the files a change touches -----------------------------------------------------

# The last full run's record, in __pycache__ beside DURATIONS: the commit it ran on, the content of each path that
# differed from that commit then, and what each test file read (`*`: may read anything).
READS = TESTS / "__pycache__" / "run-reads.json"
RECORDER = TESTS / "record_reads"
# A change to these changes how every file runs or is recorded.
RUN_EVERYTHING = ("tests/run.py", "tests/helpers.py", "tests/record_reads/")


def git(*args: str) -> str | None:
    """git's output in the checkout, or None when git fails or is missing."""
    try:
        done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=False)
    except OSError:
        return None
    return os.fsdecode(done.stdout) if done.returncode == 0 else None


def digest(rel: str) -> str | None:
    """The sha256 of a file of the checkout; None when it is missing."""
    try:
        return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    except OSError:
        return None


def status_since(commit: str) -> dict[str, str] | None:
    """Each path that differs between `commit` and the working tree, with git's status letter (A added, D deleted, M
    and the rest changed), untracked files as A; None when git cannot tell."""
    diff = git("diff", "--name-status", "--no-renames", "--relative", "-z", commit, "--")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
    if diff is None or untracked is None:
        return None
    fields = diff.split("\0")
    out = {fields[i + 1]: fields[i][:1] for i in range(0, len(fields) - 1, 2) if fields[i]}
    return out | {p: "A" for p in untracked.split("\0") if p}


def snapshot() -> dict | None:
    """Where a full run starts: its commit, and the content of every path that differs from it."""
    head = git("rev-parse", "--verify", "HEAD")
    status = status_since("HEAD")
    if head is None or status is None:
        return None
    return {"head": head.strip(), "python": list(sys.version_info[:2]), "dirty": {p: digest(p) for p in sorted(status)}}


def read_log(path: Path) -> list[str]:
    try:
        return sorted({line for line in path.read_text(encoding="utf-8", errors="surrogateescape").splitlines() if line})
    except OSError:
        return ["*"]


def strict_reads() -> bool:
    """Whether this interpreter imports aidd from the checkout with no PYTHONPATH (an editable install): then a Python
    process that does not record its reads may read the checkout without naming it."""
    code = "import importlib.util as u; s = u.find_spec('aidd'); print(s.origin if s and s.origin else '')"
    done = subprocess.run([sys.executable, "-I", "-c", code], cwd=ROOT, capture_output=True, text=True, check=False)
    origin = done.stdout.strip()
    return done.returncode != 0 or (bool(origin) and Path(origin).resolve().is_relative_to(ROOT))


def recording_env(log: Path, strict: bool) -> dict[str, str]:
    env = dict(os.environ, TESTS_READS_LOG=str(log), TESTS_READS_MAIN="1")
    env["PYTHONPATH"] = os.pathsep.join([str(RECORDER), *[p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]])
    if strict:
        env["TESTS_READS_STRICT"] = "1"
    return env


def keep_reads(start: dict, results: list[Result], logs: Path) -> None:
    """Record what each file read. A file that failed may have stopped before it read what it needs, so it may read
    anything. Only `--changed` reads the record, so a write that fails is skipped."""
    files = {r.name: read_log(logs / f"{r.name}.log") if r.passed else ["*"] for r in results}
    try:
        READS.parent.mkdir(exist_ok=True)
        READS.write_text(json.dumps(start | {"files": files}, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def changed_since(record: dict, base: str | None) -> tuple[set[str], set[str]] | str:
    """(the paths that changed since the record, those of them added or removed); with `base`, also every path the
    branch changes since it left `base`. A string says why it cannot tell."""
    status = status_since(record["head"])
    if status is None:
        return f"git cannot compare the working tree with {record['head'][:12]}, where the last full run started"
    dirty: dict[str, str | None] = record["dirty"]
    changed, moved = set(), set()
    for rel in set(status) | set(dirty):
        now = digest(rel)
        if rel in dirty:
            if now == dirty[rel]:
                continue  # as it was when the last full run read it
            existed = dirty[rel] is not None
        else:
            existed = status[rel] != "A"
        changed.add(rel)
        if existed != (now is not None):
            moved.add(rel)
    if base:
        fork = git("merge-base", base, "HEAD")
        branch = status_since(fork.strip()) if fork else None
        if branch is None:
            return f"git cannot find where this branch left {base}"
        changed |= set(branch)
        moved |= {rel for rel, letter in branch.items() if letter in "AD"}
    return changed, moved


def affected(record: dict, changed: set[str], moved: set[str], every: list[str]) -> set[str]:
    """The test files a change can affect: those that read a changed path, checked whether a path added or removed
    exists, listed a folder it is in (a new folder shows in its parent's list), or may read anything; a changed test
    file; and any file the record does not know."""
    moves = {"?" + rel for rel in moved} | {str(folder) + "/" for rel in moved for folder in Path(rel).parents}
    out = {name for name, reads in record["files"].items() if "*" in reads or not changed.isdisjoint(reads) or not moves.isdisjoint(reads)}
    out |= {Path(rel).stem for rel in changed if rel.startswith("tests/test_") and rel.endswith(".py")}
    out |= set(every) - set(record["files"])
    return out & set(every)


def select_changed(base: str | None) -> tuple[list[str] | None, str]:
    """The test files to run for `--changed`, None for all of them, and why."""
    try:
        record = json.loads(READS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "no record of what each test file reads yet: a full run, `python3 tests/run.py`, makes one"
    if record.get("python") != list(sys.version_info[:2]):
        return None, "the last full run used another Python"
    found = changed_since(record, base)
    if isinstance(found, str):
        return None, found
    changed, moved = found
    if any(rel.startswith(RUN_EVERYTHING) for rel in changed):
        return None, "the runner or the shared helpers changed"
    every = [p.stem for p in TESTS.glob("test_*.py")]
    picked = sorted(affected(record, changed, moved, every))
    return picked, f"{len(picked)} of {len(every)} test files read what changed in {len(changed)} paths since the last full run"


def references_note() -> str:
    """A line naming each skill reference that is past its cap, or "" when none is."""
    import budgets  # beside this file

    past = budgets.references_past_cap(ROOT / ".agents" / "skills" / "aidd" / "references")
    return (
        f"  References past their cap, still passing on the headroom (a note, not a failure): {', '.join(past)}. Tighten other words before the next addition."
        if past
        else ""
    )


def budget_report(results: list[Result], wall: float) -> list[str]:
    """The test budget, as lines to print: each file over FILE_BUDGET_SECONDS, and the wall time against
    WALL_BUDGET_SECONDS."""
    slow = sorted((r for r in results if r.seconds > FILE_BUDGET_SECONDS), key=lambda r: r.seconds, reverse=True)
    lines = [f"\nThe test budget: {WALL_BUDGET_SECONDS // 60} minutes for the whole suite, {FILE_BUDGET_SECONDS}s for one file (a report, not a failure)."]
    over = wall - WALL_BUDGET_SECONDS
    lines.append(f"  The suite took {wall:.1f}s, " + (f"{over:.1f}s over the budget." if over > 0 else "inside the budget."))
    if note := references_note():
        lines.append(note)
    if slow:
        lines.append(f"  {len(slow)} files took more than {FILE_BUDGET_SECONDS}s: " + ", ".join(f"{r.name} ({r.seconds:.0f}s)" for r in slow))
    return lines


def coverage_summary() -> str:
    """Line coverage and branch coverage on their own, for each area the floors name. It combines what the files recorded
    (`--keep`, so CI's own `coverage combine` still finds it); the floors stay `tests/coverage_floors.py`'s to check."""
    done = subprocess.run([sys.executable, "-m", "coverage", "combine", "--keep", "--quiet"], cwd=ROOT, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip().splitlines()
        return (
            f"Coverage not summed up ({said[-1] if said else 'coverage failed'}). Run `python3 -m coverage combine`, then `python3 tests/coverage_floors.py`."
        )
    import coverage_floors  # beside this file

    lines = ["Coverage, lines and branches on their own (a floor holds for both together; `python3 tests/coverage_floors.py` checks it):"]
    for what, include, floor in coverage_floors.FLOORS:
        line_pct, branch_pct = coverage_floors.separately(include)
        lines.append(f"  {what}: lines {line_pct}, branches {branch_pct} (floor {floor}%)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the test files in parallel, one process each.")
    parser.add_argument("names", nargs="*", metavar="FILE", help="test files to run, such as test_autopilot (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2, help="files at once (default: the number of cores)")
    parser.add_argument("--coverage", action="store_true", help="run each file under `coverage run -p`; combine with `coverage combine`")
    parser.add_argument("--slowest", type=int, default=10, metavar="N", help="list the N slowest files at the end (default 10)")
    parser.add_argument("--changed", action="store_true", help="run only the files that read what changed since the last full run")
    parser.add_argument("--base", metavar="REF", help="with --changed, also what the branch changes since it left REF, such as main")
    args = parser.parse_args(argv)
    if args.base and not args.changed:
        parser.error("--base goes with --changed: python3 tests/run.py --changed --base main")
    if args.changed and args.names:
        parser.error("--changed picks the files itself: name files or pass --changed, not both")

    names = args.names
    if args.changed:
        picked, why = select_changed(args.base)
        print(f"--changed: {why}." + (" Running every file." if picked is None else ""), flush=True)
        if picked == []:
            print(f"--changed: no test file reads what changed, so it runs the smoke set instead of nothing: {', '.join(SMOKE_FILES)}.", flush=True)
            picked = list(SMOKE_FILES)
        names = picked or []
    todo = files(names)
    # Only a run of every file records what each reads, so the record always comes from one commit and one tree.
    full = not names and not args.coverage
    start_state = snapshot() if full else None
    logs = tempfile.TemporaryDirectory(prefix="aidd-test-reads-") if start_state else None
    strict = strict_reads() if logs else False

    start = time.monotonic()
    results: list[Result] = []
    # Threads only wait: each file runs in its own process. Each line prints as its file finishes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        running = [pool.submit(run_one, path, args.coverage, recording_env(Path(logs.name) / f"{path.stem}.log", strict) if logs else None) for path in todo]
        for future in concurrent.futures.as_completed(running):
            result = future.result()
            results.append(result)
            mark = "ok  " if result.passed else "FAIL"
            print(f"{mark} {result.name} ({result.ran} tests, {result.seconds:.1f}s)" + (" TIMED OUT" if result.timed_out else ""), flush=True)
    wall = time.monotonic() - start
    keep_durations(results)
    if logs and start_state:
        keep_reads(start_state, results, Path(logs.name))
        logs.cleanup()

    failed = [r for r in results if not r.passed]
    for r in failed:
        print(f"\n{'=' * 70}\n{r.name}\n{'=' * 70}\n{r.output.rstrip()}")
    print(f"\nThe slowest {min(args.slowest, len(results))} files:")
    for r in sorted(results, key=lambda r: r.seconds, reverse=True)[: args.slowest]:
        print(f"  {r.seconds:6.1f}s  {r.name} ({r.ran} tests)")
    ran, skipped = sum(r.ran for r in results), sum(r.skipped for r in results)
    if args.coverage:
        print("\n" + coverage_summary())
    print(f"\nRan {ran} tests in {len(results)} files in {wall:.1f}s, {args.jobs} at a time")
    if not names:
        print("\n".join(budget_report(results, wall)))
    if failed:
        print(f"FAILED: {', '.join(r.name for r in failed)}")
        if any(r.timed_out for r in failed):
            print(f"TIMED OUT after {FILE_TIMEOUT_SECONDS}s: {', '.join(r.name for r in failed if r.timed_out)}")
        return 1
    print(f"OK (skipped={skipped})" if skipped else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
