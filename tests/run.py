"""Run the test suite in parallel: each test file in its own process, as many at once as the machine has cores.

    python3 tests/run.py                      # every test file
    python3 tests/run.py -j 4                 # four at a time
    python3 tests/run.py test_autopilot test_gate_rules
    python3 tests/run.py --coverage           # each file under `coverage run -p`, combined into .coverage at the end
    python3 tests/run.py --changed            # the files that read what changed since the last full run, plus WHOLE_TREE; see below
    python3 tests/run.py --changed --base main   # and what the branch changes since it left main
    AIDD_BROWSER_TESTS=1 python3 tests/run.py --browser   # only the files that drive a real browser

Each file runs as `python -m unittest discover -s tests -p <file>`, the way the whole suite runs, so a file sees the same
set-up as under `discover`; a process per file keeps the globals, the working directory, and the environment one test
patches away from every other file. It uses only the standard library. The suite in one process,
`python3 -m unittest discover -s tests`, stays the reference: this runner only spreads the same files over cores.

A full run also records which files of the checkout each test file reads (tests/record_reads/sitecustomize.py), in the
git folder the checkouts of one repository share, so a fresh worktree finds the record of the last full run anywhere. `--changed`
runs a file when it read a path that changed since that run, or may read anything, and it always runs the checks that read the
whole repository (WHOLE_TREE, and the fast content checks in SMOKE_FILES): a change anywhere can break them, and a record
cannot say which. With no record, it picks the files whose text names a changed path instead, and says so; it never runs nothing,
and it runs every file only when it cannot tell what changed or the runner itself changed. pytest-testmon does the same
from coverage, but it misses every file a child process reads, and these tests start aidd as a child. A full run ends
with the files over FILE_BUDGET_SECONDS and its wall time against WALL_BUDGET_SECONDS: a report, never a failure.

Every run fails when it leaves a tracked file of the repository changed (compared with the tree before the run, so work
in progress is not a failure), and lists each path with the test files that ran when it changed: a test writes only to a temporary folder.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no shared turn there
    fcntl = None  # type: ignore[assignment]

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
# The checks that read the whole repository by design, by the kind of miss each catches (sorted by kind, then by test file).
# A change anywhere can break them, so `--changed` always runs them, even where the read record cannot say which change
# reaches them. tests/seeded_misses.py seeds each kind into a scratch copy and shows the run fails, and tests/test_runner_prereport.py
# checks that the table and the seeds cover each other.
WHOLE_TREE: dict[str, tuple[str, ...]] = {
    "a command in agent text that asks by surprise, or a flag a doc names that does not exist": ("command_guide", "instructed_commands"),
    "a core file that names a framework or tool": ("overfit",),
    "a field name against the naming rules": ("field_names",),
    "a finding code with no row": ("enum_owners", "findings"),
    "a function or file past its shape ceiling": ("code_shape",),
    "a glossary term with no `aidd explain` answer": ("explain",),
    "a long sentence copied between pages, or a page under its share of short sentences": ("docs", "plain_language"),
    "a module that reads a repository file outside the safe reader": ("setup_reads",),
    "a package door that exports a name only its own package reads, or lists names out of order": ("named_things", "package_doors"),
    "a pattern the code-scanning classes forbid": ("code_scanning_classes",),
    "a pinned public fact": ("doc_currency", "front_door", "plugin_channel", "release_surface"),
    "a role file or reference over its byte budget": ("loop_contract", "team", "team_roles_and_flows"),
    "a schema keyword the bundled checker does not support": ("schema_constraints",),
    "a work-item field word in the risk code": ("workitems",),
    "an eval grader copy that differs from its library, or a fixture that is no valid repository": (
        "eval_fixtures_plugin",
        "eval_fixtures_team_1",
        "eval_fixtures_team_2",
        "eval_fixtures_team_3",
        "eval_grader_library",
    ),
    "an unused function in src/aidd": ("untrusted_input",),
    "generated docs out of date (`aidd gen-docs --check`, which test_repository_consistency runs)": ("repository_consistency",),
}
# Every file `--changed` runs whatever changed: the table above and the smoke set, once each.
ALWAYS = tuple(sorted({*SMOKE_FILES, *(name for names in WHOLE_TREE.values() for name in names)}))


@dataclass
class Result:
    name: str
    code: int
    seconds: float
    ran: int
    skipped: int
    output: str
    timed_out: bool = False
    started: float = 0.0  # wall-clock seconds (time.time()) when the file's process started and ended, to name who wrote a path
    ended: float = 0.0

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
    """Record each file's seconds for the next run's order, and forget each file that no longer exists. Only the order
    depends on it, so a write that fails is skipped."""
    every = {p.stem for p in TESTS.glob("test_*.py")}
    data = {name: seconds for name, seconds in last_durations().items() if name in every} | {r.name: round(r.seconds, 1) for r in results}
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
    start, wall_start = time.monotonic(), time.time()
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
    return Result(path.stem, proc.returncode, time.monotonic() - start, ran, skipped, output, timed_out, wall_start, time.time())


# ---- What each test file reads, and the files a change touches -----------------------------------------------------

# The last full run's record: the commit it ran on, the content of each path that differed from that commit then, and what
# each test file read (`*`: may read anything). It lives in the git folder that every checkout and worktree of the repository
# shares (`reads_path`), so a fresh worktree finds the record of the last full run made anywhere; READS, in __pycache__
# beside DURATIONS, is where it goes with no git. A record names a commit and the paths that differed, so it holds in any checkout that has the commit.
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


# A run of more files than this takes the turn below, so two suites never run at once on one machine: the suite uses every
# core, and two of them time files out that pass alone. A run of a few named files does not wait, and neither does the
# `--changed` floor: measured on 2026-11-12, it is 55 of 354 files and 260 of the suite's 2,258 file-seconds (ALWAYS, the
# files that may read anything, and the files the record does not know yet). 64 lets a change that adds a few readers to that
# floor run beside a full run, at about an eighth of its load, while a run that reads more, such as a one-line change to a skill
# reference (125 files), waits its turn.
TURN_ABOVE_FILES = 64


@contextlib.contextmanager
def turn(count: int) -> Iterator[None]:
    """Hold the one turn the checkouts of this repository share while a large run goes, waiting for a run in another
    checkout to end first and saying so. The lock is a file in the git folder they share; where there is none, or the
    platform has no `fcntl`, the run goes at once."""
    common = git("rev-parse", "--git-common-dir")
    if fcntl is None or count <= TURN_ABOVE_FILES or not (common and common.strip()):
        yield
        return
    with open(ROOT / common.strip() / "aidd-test-turn.lock", "a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.seek(0)
            print(f"Another test run holds the turn ({lock.read().strip() or 'unknown'}). Waiting for it to end.", flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
        lock.seek(0)
        lock.truncate()
        lock.write(f"pid {os.getpid()} in {ROOT}")
        lock.flush()
        try:
            yield
        finally:
            lock.seek(0)
            lock.truncate()
            fcntl.flock(lock, fcntl.LOCK_UN)


def reads_path() -> Path:
    """Where the read record is kept: `aidd-test-reads.json` in the git folder the repository's checkouts share, else READS."""
    common = git("rev-parse", "--git-common-dir")
    return ROOT / common.strip() / "aidd-test-reads.json" if common and common.strip() else READS


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
    anything. Only `--changed` reads the record, so a write that fails is skipped. The file is replaced whole, so two
    checkouts that finish a full run together leave one record, never half of each."""
    files = {r.name: read_log(logs / f"{r.name}.log") if r.passed else ["*"] for r in results}
    target = reads_path()
    try:
        target.parent.mkdir(exist_ok=True)
        part = target.with_name(f"{target.name}.{os.getpid()}")
        part.write_text(json.dumps(start | {"files": files}, indent=0, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(part, target)
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
    return (add_branch(base, changed, moved) or (changed, moved)) if base else (changed, moved)


def add_branch(base: str, changed: set[str], moved: set[str]) -> str | None:
    """Add every path the branch changes since it left `base` to `changed` and `moved`; a string says why it cannot."""
    fork = git("merge-base", base, "HEAD")
    branch = status_since(fork.strip()) if fork else None
    if branch is None:
        return f"git cannot find where this branch left {base}"
    changed |= set(branch)
    moved |= {rel for rel, letter in branch.items() if letter in "AD"}
    return None


def affected(record: dict, changed: set[str], moved: set[str], every: list[str]) -> set[str]:
    """The test files a change can affect: those that read a changed path, checked whether a path added or removed
    exists, listed a folder it is in (a new folder shows in its parent's list), or may read anything; a changed test
    file; and any file the record does not know."""
    moves = {"?" + rel for rel in moved} | {str(folder) + "/" for rel in moved for folder in Path(rel).parents}
    out = {name for name, reads in record["files"].items() if "*" in reads or not changed.isdisjoint(reads) or not moves.isdisjoint(reads)}
    out |= {Path(rel).stem for rel in changed if rel.startswith("tests/test_") and rel.endswith(".py")}
    out |= set(every) - set(record["files"])
    return out & set(every)


def needles(rel: str) -> list[tuple[str, ...]]:
    """What a test file's text can name a changed path by, each a group of words that must all appear: the path, its file
    name, and for a module of src/ its dotted name, or its package's dotted name with the module's name (`from aidd.evals
    import scoring`). Never the top-level `aidd` alone, which every test names."""
    path = Path(rel)
    found: list[tuple[str, ...]] = [(rel,)] + ([(path.name,)] if path.name != "__init__.py" else [])
    if path.suffix == ".py" and path.parts[0] == "tests":
        found.append((path.stem,))  # a test module is imported by its bare name
    elif path.suffix == ".py":
        parts = list(path.with_suffix("").parts)
        parts = parts[1:] if parts[0] == "src" else parts
        module = None if parts[-1] == "__init__" else parts[-1]
        parts = parts[:-1]
        whole = [*parts, module] if module else parts
        if len(whole) > 1:
            found.append((".".join(whole),))
        if module and len(parts) > 1:
            found.append((".".join(parts), module))
    return found


def named_by(changed: set[str], every: list[str]) -> set[str]:
    """With no read record: the test files whose text names a changed path (`needles`). It over-picks, by design: a
    file that names a module's package and its name may mean another thing by the name."""
    groups = [group for rel in sorted(changed) for group in needles(rel)]
    out = set()
    for name in every:
        try:
            text = (TESTS / f"{name}.py").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(all(word in text for word in group) for group in groups):
            out.add(name)
    return out


def usable_record() -> tuple[dict | None, str]:
    """The read record when it can serve this run, else None and why not."""
    try:
        record = json.loads(reads_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "no record of what each test file reads yet (a full run, `python3 tests/run.py`, makes one)"
    if record.get("python") != list(sys.version_info[:2]):
        return None, "the last full run used another Python"
    return record, ""


def select_changed(base: str | None) -> tuple[list[str] | None, str]:
    """The test files to run for `--changed`, None for all of them, and why. Always the checks of the whole repository
    (ALWAYS), and beside them the files that read what changed: by the record of the last full run when there is one,
    else the files whose text names a changed path. It picks every file only when git cannot say what changed or the
    runner itself did."""
    every = [p.stem for p in TESTS.glob("test_*.py")]
    always = {name for name in ALWAYS if f"test_{name}" in every}
    record, why = usable_record()
    found = changed_since(record, base) if record else why
    if isinstance(found, str):
        record, why = None, found
        status = status_since("HEAD")
        if status is None:
            return None, f"git cannot tell what changed here ({why})"
        changed, moved = set(status), {rel for rel, letter in status.items() if letter in "AD"}
        if base and (failed := add_branch(base, changed, moved)):
            return None, failed
    else:
        changed, moved = found
    if any(rel.startswith(RUN_EVERYTHING) for rel in changed):
        return None, "the runner or the shared helpers changed"
    if record:
        picked = affected(record, changed, moved, every)
        how = f"read what changed in {len(changed)} paths since the last full run"
    else:
        picked = {Path(rel).stem for rel in changed if rel.startswith("tests/test_") and rel.endswith(".py")} | named_by(changed, every)
        how = f"name what changed in {len(changed)} paths ({why}, so a full run makes this exact)"
        if not changed and not base:
            how += "; the tree matches HEAD, so after a commit add --base <the commit you started from>"
    out = sorted((picked & set(every)) | {f"test_{n}" for n in always})
    return out, f"{len(out)} of {len(every)} test files: {len(picked & set(every))} {how}, and the checks of the whole repository, which run every time"


def references_note() -> str:
    """A line naming each reference and template that is near the limit for its class, or "" when none is."""
    import budgets  # beside this file

    skill = ROOT / ".agents" / "skills" / "aidd"
    near = budgets.near_class_limit(skill / "references", skill / "assets")
    return (
        f"  Near the limit for their class, still passing (a note, not a failure): {', '.join(near)}. Restructure by topic before the next addition."
        if near
        else ""
    )


def sections_note() -> str:
    """A line naming each section past budgets.SECTION_TOKENS, or "" when none is."""
    import budgets  # beside this file

    long = budgets.long_sections(budgets.signal_files(ROOT), ROOT)
    return f"  Sections past {budgets.SECTION_TOKENS:,} tokens (a note, not a failure): {'; '.join(long)}. Split the section by topic." if long else ""


def budget_report(results: list[Result], wall: float) -> list[str]:
    """The test budget, as lines to print: each file over FILE_BUDGET_SECONDS, and the wall time against
    WALL_BUDGET_SECONDS."""
    slow = sorted((r for r in results if r.seconds > FILE_BUDGET_SECONDS), key=lambda r: r.seconds, reverse=True)
    lines = [f"\nThe test budget: {WALL_BUDGET_SECONDS // 60} minutes for the whole suite, {FILE_BUDGET_SECONDS}s for one file (a report, not a failure)."]
    over = wall - WALL_BUDGET_SECONDS
    lines.append(f"  The suite took {wall:.1f}s, " + (f"{over:.1f}s over the budget." if over > 0 else "inside the budget."))
    for note in (references_note(), sections_note()):
        if note:
            lines.append(note)
    if slow:
        lines.append(f"  {len(slow)} files took more than {FILE_BUDGET_SECONDS}s: " + ", ".join(f"{r.name} ({r.seconds:.0f}s)" for r in slow))
    return lines


def coverage_summary() -> str:
    """Line coverage and branch coverage on their own, for each area the floors name. It combines what the files recorded
    into `.coverage`, which `coverage report` and `tests/coverage_floors.py` then read, so nothing combines it again: a
    second `coverage combine` finds no data and fails. The floors stay `tests/coverage_floors.py`'s to check."""
    done = subprocess.run([sys.executable, "-m", "coverage", "combine", "--quiet"], cwd=ROOT, capture_output=True, text=True, check=False)
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


# The module every browser test drives Chrome with, itself or through a module's shared set-up.
BROWSER_DRIVER = "browser_driver"


def imported_modules(source: str) -> set[str]:
    """The top-level name of every module a file imports, at any depth and in any form (`import a, b`, `from a.b import c`)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()  # the file fails when it runs, with the error that says why
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name.partition(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.partition(".")[0])
    return names


def browser_files() -> list[str]:
    """The test files that drive a real browser (`--browser`): each imports `browser_driver`, itself or through another
    test module, such as `viewer_browser`. CI runs them in a job of their own, without coverage, because the Python they
    reach writes the pages, which other files cover. Every other job runs them with the browser tests skipped."""
    imports = {p.stem: imported_modules(p.read_text(encoding="utf-8")) for p in TESTS.glob("*.py")}
    drives = {BROWSER_DRIVER}
    while grown := {name for name, used in imports.items() if name not in drives and used & drives}:
        drives |= grown
    return sorted(name for name in drives if name.startswith("test_"))


# ---- A run never leaves a tracked file changed ---------------------------------------------------------------------


def tracked_state() -> dict[str, tuple[str, str | None]] | None:
    """Each tracked path that differs from HEAD or the index, with git's two status letters and a digest of its content
    (None when it is gone): the content, because a file that was dirty and is dirty again in another way reads the same
    in `git status`. None when git cannot tell."""
    top = git("rev-parse", "--show-toplevel")
    out = git("status", "--porcelain=v1", "-z", "--untracked-files=no", "--no-renames")
    if not top or out is None:
        return None
    base = Path(top.strip())
    state: dict[str, tuple[str, str | None]] = {}
    for entry in out.split("\0"):
        if len(entry) > 3:
            try:
                content = hashlib.sha256((base / entry[3:]).read_bytes()).hexdigest()
            except OSError:
                content = None
            state[entry[3:]] = (entry[:2], content)
    return state


def tracked_changes(before: dict, after: dict, results: list[Result]) -> list[str]:
    """One line for each tracked path whose state after the run differs from before it, with the test files that ran when
    it was written (its modification time inside their run, a second either side), or all of them when it is gone."""
    top = git("rev-parse", "--show-toplevel")
    base = Path(top.strip()) if top else ROOT
    lines = []
    for rel in sorted(before.keys() | after.keys()):
        if before.get(rel) == after.get(rel):
            continue
        try:
            written = (base / rel).stat().st_mtime
            ran = [r.name for r in results if r.started - 1 <= written <= r.ended + 1]
            who = ", ".join(sorted(ran)) if ran else "none was running then, so something else wrote it"
        except OSError:
            who = "it is gone, so any file that ran may have removed it: " + ", ".join(sorted(r.name for r in results))
        lines.append(f"  {rel}: written while these ran: {who}")
    return lines


# The files that time something: they run alone, after the others, because a time means something only when nothing else
# competes for the CPU.
ALONE = frozenset({"test_work_page_speed"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the test files in parallel, one process each.")
    parser.add_argument("names", nargs="*", metavar="FILE", help="test files to run, such as test_autopilot (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2, help="files at once (default: the number of cores)")
    parser.add_argument("--coverage", action="store_true", help="run each file under `coverage run -p`, and combine them into .coverage at the end")
    parser.add_argument("--slowest", type=int, default=10, metavar="N", help="list the N slowest files at the end (default 10)")
    parser.add_argument(
        "--changed",
        action="store_true",
        help="run the files that read what changed since the last full run, and the checks of the whole repository (WHOLE_TREE)",
    )
    parser.add_argument("--base", metavar="REF", help="with --changed, also what the branch changes since it left REF, such as main")
    parser.add_argument("--browser", action="store_true", help="run only the files that drive a real browser; needs AIDD_BROWSER_TESTS=1")
    args = parser.parse_args(argv)
    if args.browser and (args.names or args.changed):
        parser.error("--browser picks the files itself: name files, pass --changed, or pass --browser, one of them")
    if args.browser and os.environ.get("AIDD_BROWSER_TESTS") != "1":
        parser.error("--browser runs the browser tests, which skip without AIDD_BROWSER_TESTS=1: AIDD_BROWSER_TESTS=1 python3 tests/run.py --browser")
    if args.base and not args.changed:
        parser.error("--base goes with --changed: python3 tests/run.py --changed --base main")
    if args.changed and args.names:
        parser.error("--changed picks the files itself: name files or pass --changed, not both")

    names = browser_files() if args.browser else args.names
    if args.changed:
        picked, why = select_changed(args.base)
        print(f"--changed: {why}." + (" Running every file." if picked is None else ""), flush=True)
        if picked == []:
            print(f"--changed: no test file reads what changed, so it runs the smoke set instead of nothing: {', '.join(SMOKE_FILES)}.", flush=True)
            picked = list(SMOKE_FILES)
        names = picked or []
    todo = files(names)
    with turn(len(todo)):
        return run_files(args, names, todo)


def run_files(args: argparse.Namespace, names: list[str], todo: list[Path]) -> int:
    """Run `todo`, report each file, and return the exit code."""
    tracked_before = tracked_state()
    # Only a run of every file records what each reads, so the record always comes from one commit and one tree.
    full = not names and not args.coverage
    start_state = snapshot() if full else None
    logs = tempfile.TemporaryDirectory(prefix="aidd-test-reads-") if start_state else None
    strict = strict_reads() if logs else False

    start = time.monotonic()
    results: list[Result] = []

    def run(path: Path) -> Result:
        return run_one(path, args.coverage, recording_env(Path(logs.name) / f"{path.stem}.log", strict) if logs else None)

    def report(result: Result) -> None:
        results.append(result)
        mark = "ok  " if result.passed else "FAIL"
        print(f"{mark} {result.name} ({result.ran} tests, {result.seconds:.1f}s)" + (" TIMED OUT" if result.timed_out else ""), flush=True)

    # Threads only wait: each file runs in its own process. Each line prints as its file finishes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, path) for path in todo if path.stem not in ALONE]):
            report(future.result())
    for path in todo:  # after the pool, one at a time, so no other file competes for the CPU
        if path.stem in ALONE:
            report(run(path))
    wall = time.monotonic() - start
    keep_durations(results)
    if logs and start_state:
        keep_reads(start_state, results, Path(logs.name))
        logs.cleanup()

    tracked_after = tracked_state() if tracked_before is not None else None
    moved_files = tracked_changes(tracked_before, tracked_after, results) if tracked_before is not None and tracked_after is not None else []
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
    if tracked_before is None or tracked_after is None:
        print("Tracked-file check skipped: git cannot tell here (not a repository, or git is missing).")
    if moved_files:
        print(
            "\nFAILED: the run changed tracked files, which a test must never do (it writes to a temporary folder). Restore a path that was clean before with `git checkout -- <path>`:"
        )
        print("\n".join(moved_files))
    if failed:
        print(f"FAILED: {', '.join(r.name for r in failed)}")
        if any(r.timed_out for r in failed):
            print(f"TIMED OUT after {FILE_TIMEOUT_SECONDS}s: {', '.join(r.name for r in failed if r.timed_out)}")
        return 1
    if moved_files:
        return 1
    print(f"OK (skipped={skipped})" if skipped else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
