"""`aidd test`: run a change's tests and write the evidence, `.aidd/evidence/evidence.json`.

Evidence is a runner's exit code bound to a commit: each command's result on the head, and for a Spec's new-behavior
commands, on the base too, where they must fail (red before green). A command that names a JUnit XML `report` adds the
failed test cases to its result (`junit.py`); the exit code stays the evidence. A summary or a chat message is never evidence. The
commands run with no credential-like variable unless the person passes one by name, and a run that writes the Spec,
its frozen files, or the config is stopped.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from aidd import __version__, config, workitems
from aidd.kernel import documents, git, globs, json_schema, processes, repo_paths
from aidd.kernel.processes import scrub_credentials, wait_unreaped
from aidd.kernel.timestamps import utc_stamp
from aidd.testing import junit, weakening

DEFAULT_TIMEOUT_SECONDS = 1800
MAX_LOG_BYTES = 10 * 1024 * 1024
CI_RUNNER_ENV = ("GITHUB_ACTIONS", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITLAB_CI", "CI_JOB_ID", "CI_JOB_URL")


def _runner() -> dict:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo, run_id = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", "")
        return {"ci": "github", "run_id": run_id, "url": f"{server}/{repo}/actions/runs/{run_id}"}
    if os.environ.get("GITLAB_CI") == "true":
        return {"ci": "gitlab", "run_id": os.environ.get("CI_JOB_ID", ""), "url": os.environ.get("CI_JOB_URL", "")}
    return {"ci": "local"}


def log_path(logs: Path, phase: str, name: str) -> Path:
    """Where one command's log goes. Names are schema-checked; this is the backstop against a name that climbs out."""
    log = logs / f"{phase}-{name}.log"
    if not log.resolve().is_relative_to(logs.resolve()):
        raise RuntimeError(f"test name {name!r} would write its log outside {logs}")
    return log


TRUNCATED = b"\n... [truncated by aidd runner: log exceeded limit] ...\n"


class _LogPump:
    """Copies a command's output into its log as it runs, up to MAX_LOG_BYTES, then reads and drops the rest, so a
    command that prints without end never fills the disk and never blocks on a full pipe."""

    def __init__(self, proc: subprocess.Popen, out) -> None:
        import threading

        self.out, self.written, self.marked, self.lock = out, 0, False, threading.Lock()
        self.fd = proc.stdout.fileno() if proc.stdout else -1
        self.proc = proc
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            try:
                chunk = os.read(self.fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            with self.lock:
                if self.out is None:
                    return
                room = MAX_LOG_BYTES - self.written
                if room > 0:
                    self.out.write(chunk[:room])
                if len(chunk) > room and not self.marked:
                    self.out.write(TRUNCATED)
                    self.marked = True
                self.written += len(chunk)

    def finish(self, grace: float = 5.0) -> None:
        """Wait for the output to end; a process that left the group and holds the pipe open is left behind after
        `grace` seconds, and nothing more reaches the log."""
        self.thread.join(grace)
        with self.lock:
            self.out = None
        if not self.thread.is_alive() and self.proc.stdout:
            self.proc.stdout.close()


def run_test_command(
    command: list[str], *, cwd: str, log: Path, timeout_seconds: float, env: dict[str, str] | None = None, pass_env: list[str] | tuple[str, ...] = ()
) -> dict:
    started = utc_stamp()
    t0 = time.monotonic()
    log.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":  # resolve npx.cmd, gradlew.bat, and other PATHEXT shims
        command = [shutil.which(command[0]) or command[0], *command[1:]]
    # The change wrote the tests it runs: they see no credential-like variable unless the person passes one by name.
    clean_env = scrub_credentials(dict(os.environ), keep=pass_env)
    for k in CI_RUNNER_ENV:
        if k in os.environ:
            clean_env[k] = os.environ[k]
    # The worktree `aidd test` runs for, on head and on base alike: the project names its database and bucket by it.
    clean_env.setdefault("AIDD_WORKTREE", worktree_slug(git.toplevel(check=False) or os.getcwd()))
    if env:
        clean_env.update(env)
    with open(log, "wb") as out:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=clean_env, start_new_session=hasattr(os, "killpg"))
        except OSError as exc:
            out.write(f"not started: {exc}\n".encode())
            return {"exit": None, "status": "not_started", "duration_seconds": 0.0, "started_at": started, "finished_at": utc_stamp()}
        pump = _LogPump(proc, out)
        exited = wait_unreaped(proc, timeout_seconds)
        # Kill the whole process group every time, so an ordinary background
        # process a test started (a dev server, a watcher) cannot outlive it,
        # while the leader is still unreaped, so the group id is still its own.
        # This is hygiene, not containment: code that leaves the group (setsid)
        # or an earlier step of the same job can still write anything. The
        # test job runs PR code and is untrusted; evidence is as honest as it.
        processes.kill_group(proc)
        proc.wait()
        pump.finish()
        code = proc.returncode if exited else None
        status = ("passed" if code == 0 else "failed") if exited else "timeout"
    return {"exit": code, "status": status, "duration_seconds": round(time.monotonic() - t0, 3), "started_at": started, "finished_at": utc_stamp()}


def worktree_slug(path: str) -> str:
    """The worktree's folder name as a slug, so a project can name its test database or bucket by it (AIDD_WORKTREE)."""
    name = Path(path).name.lower()
    return "".join(ch if ch.isalnum() else "-" for ch in name).strip("-") or "main"


def select_tests(commands: list[dict], paths: list[str]) -> list[dict]:
    """Commands that apply to this diff: those without when_changed, and those whose globs match a changed path.
    Matching ignores case: a pattern must not miss `DB/` for `db/`."""
    return [c for c in commands if not c.get("when_changed") or any(globs.match_any(c["when_changed"], p, fold_case=True) for p in paths)]


def changed_paths(files: list[dict]) -> list[str]:
    """Every path a diff touches, including rename sources."""
    return sorted({f["path"] for f in files} | {f["previous_path"] for f in files if f.get("previous_path")})


def spec_phase(paths: list[str], frozen: list[str], task_scopes: list[list[str]]) -> bool:
    """Whether a Spec-backed change is still in its Spec phase: every changed path is the Spec or a file it freezes, and
    some Task's scope has no change yet. Its tests are expected to fail on head until Implement."""
    if not paths or not all(globs.match_any(frozen, p) for p in paths):
        return False
    return any(not any(globs.match_any(scope, p) for p in paths) for scope in task_scopes)


def required_tests(
    config_tests: list[dict], declared: list[dict], source: str, paths: list[str], route: str | None = None
) -> tuple[list[tuple[dict, str]], list[str]]:
    """The (command, source) pairs this diff must run, and any names declared twice. On the emergency route the
    repository suite is its `smoke: true` commands when it marks any, and the change's own commands add to them."""
    if route == "emergency" and any(c.get("smoke") for c in config_tests):
        config_tests = [c for c in config_tests if c.get("smoke")]
    pairs = [(c, "config") for c in config_tests] + [(c, source) for c in declared]
    names = [c["name"] for c, _ in pairs]
    dupes = sorted({n for i, n in enumerate(names) if n in names[:i]})
    selected = select_tests([c for c, _ in pairs], paths)
    return [(c, src) for c, src in pairs if any(c is s for s in selected)], dupes


def _declarations(repo: str, base_sha: str, head_sha: str, *, spec: str | None) -> tuple[config.Config, dict | None, str | None]:
    """The config in this worktree, the Spec's test declaration, and the Spec's path: the one given, else the one Spec
    the branch adds or changes (None when there is none, or more than one)."""
    path = Path(repo) / config.CONFIG_PATH
    if not path.is_file():
        raise config.ConfigError(f"no {config.CONFIG_PATH} here; `aidd init` writes one")
    cfg = config.load_file(config.CONFIG_PATH, repo)
    files = git.numstat(base_sha, head_sha, repo)
    found = [repo_paths.repo_path(spec)] if spec else workitems.find_specs_in_diff(files, cfg.specs_dir, lambda p: git.show(head_sha, p, repo))
    spec = found[0] if len(found) == 1 else None
    if not spec:
        return cfg, None, None
    text = git.show(head_sha, spec, repo)
    if text is None:
        raise documents.DocumentError(f"{spec} is not in the head commit; commit it first")
    # The Spec names the commands and their log files: it must pass its schema before anything runs.
    declared, _, errs = workitems.load_object(text, spec)
    if errs:
        raise documents.DocumentError("; ".join(errs))
    return cfg, declared, spec


def _run(c: dict, phase: str, source: str, cwd: str, logs: Path, pass_env: list[str] | tuple[str, ...]) -> dict:
    """One command's result. On head, a failure is tried again up to its `retries`: every attempt is kept, and a pass
    after a failure is marked flaky. A red run on the base commit is tried once: a retry could turn a flaky test red."""
    retries = int(c.get("retries", 0) or 0) if phase == "green" else 0
    attempts: list[dict] = []
    report = c.get("report")
    for i in range(retries + 1):
        log = log_path(logs, phase, c["name"] if i == 0 else f"{c['name']}.attempt-{i + 1}")
        before = junit.stamp(Path(cwd), report) if report else None
        r = run_test_command(c["command"], cwd=cwd, log=log, timeout_seconds=c.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS), pass_env=pass_env)
        if report:  # read where the command ran: a red run's tree is gone afterwards
            r["report"] = junit.read_report(Path(cwd), report, before)
        attempts.append({"log": log.relative_to(logs.parent).as_posix(), **r})
        if r["status"] == "passed":
            break
    out = {"name": c["name"], "source": source, "command": c["command"], "red_green": phase, **attempts[-1]}
    if len(attempts) > 1:
        out["attempts"] = attempts
        out["flaky"] = attempts[-1]["status"] == "passed"
    return out


def _materialize(repo: str, head_sha: str, test_files: list[str], dest_root: str) -> None:
    """The Spec's test files from head, written over the base checkout at `dest_root`. The backstop, as in `log_path`: a
    path that climbs out of `dest_root`, by `..` or through a symlink the base commit holds, is refused before a write."""
    root = Path(dest_root).resolve()
    for rel in test_files:
        content = git.show_bytes(head_sha, rel, repo)
        if content is None:
            raise git.GitError(f"{rel} is not in {head_sha[:12]}")
        dest = Path(dest_root) / rel
        if not dest.resolve().is_relative_to(root):
            raise RuntimeError(
                f"test file {rel!r} would be written outside {dest_root}, through `..` or a symlink the base commit holds. "
                "Rename it in the Spec's `tests.files` to a path inside the repository that no symlink leads out of, and run `aidd test` again"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)


def _red_runs(
    repo: str,
    base_sha: str,
    head_sha: str,
    tests: dict,
    commands: list[dict],
    logs: Path,
    in_place: bool,
    pass_env: list[str] | tuple[str, ...] = (),
    patterns: list[str] | None = None,
) -> list[dict]:
    test_files = workitems.tests_files(tests.get("files", []), git.ls_tree(head_sha, repo))
    results: list[dict] = []

    def run_all(cwd: str) -> None:
        _materialize(repo, head_sha, test_files, cwd)
        # Checked here, in the red tree, before an in-place run's forced checkout would discard what a command wrote.
        before = _snapshot(cwd, patterns or [])
        for c in commands:
            results.append(_run(c, "red", "spec", cwd, logs, pass_env))
            _check_untouched(before, cwd, patterns or [], f"the red run of {c.get('name')}")

    if in_place:
        # CI workspaces keep installed dependencies (node_modules, .venv) this way. Tests may have
        # rewritten tracked files (snapshots, lockfiles); a forced checkout discards those edits.
        branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()
        try:
            git.run(["checkout", "--quiet", "--force", "--detach", base_sha], repo)
            run_all(repo)
        finally:
            back = ["checkout", "--quiet", "--force", branch] if branch else ["checkout", "--quiet", "--force", "--detach", head_sha]
            git.run(back, repo)
        return results
    tmp = tempfile.mkdtemp(prefix="aidd-red-")
    try:
        git.run(["worktree", "add", "--detach", "--force", tmp, base_sha], repo)
        run_all(tmp)
    finally:
        git.run(["worktree", "remove", "--force", tmp], repo, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    return results


MAX_DIRTY_PATHS = 50  # the evidence names this many; `dirty_tree` says there were any


def dirty_paths(repo: str, out: Path) -> list[str]:
    """What the tree holds that its head commit does not, so tests run in it prove nothing about that commit: tracked
    changes, staged or not, untracked files the repository's .gitignore files do not ignore, and files git is told not
    to look at (`--assume-unchanged`, or `--skip-worktree` on a file that is there). `.git/info/exclude` and a person's
    global excludes never hide a file, because CI reads neither. `aidd test`'s own output folder is left out."""
    top = Path(git.toplevel(repo, check=True)).resolve()
    found = set(git.dirty(str(top)))  # porcelain paths are from the top, as ls-files' are run there
    # Without --exclude-standard, ls-files reads only the ignore files it is named: each folder's .gitignore.
    found.update(p for p in git.run(["ls-files", "--others", "-z", "--exclude-per-directory=.gitignore"], str(top)).split("\0") if p)
    for entry in git.run(["ls-files", "-v", "-z"], str(top)).split("\0"):
        tag, name = entry[:1], entry[2:]
        if name and (tag.islower() or (tag == "S" and os.path.lexists(top / name))):
            found.add(name)
    own = out.relative_to(top).as_posix() + "/" if out.is_relative_to(top) else None
    return sorted(p for p in found if not (own and (p + "/").startswith(own)))


def working_tree_paths(repo: str, base_sha: str) -> list[str]:
    """Every path the working tree changes against the base: committed, staged, unstaged, and untracked but not ignored."""
    tracked = git.run(["diff", "--name-only", "--no-renames", "-z", base_sha, "--"], repo).split("\0")
    untracked = git.run(["ls-files", "-z", "--others", "--exclude-standard"], repo).split("\0")
    return sorted({p for p in tracked + untracked if p})


def select_changed(commands: list[tuple[dict, str]], declared: dict | None, paths: list[str]) -> list[tuple[dict, str]]:
    """The commands `aidd test --changed` runs for these working-tree paths.

    A command with `when_changed` runs when it matches (required_tests already checked). A Spec's command without it
    runs when a path is inside a Task's scope or the Spec's test files, design files, and frozen docs. Any other command applies to every
    path, so it runs whenever something changed."""
    if not paths:
        return []
    d = declared or {}
    scopes = [s for task in d.get("tasks") or [] for s in task.get("scope") or []]
    scopes += list((d.get("tests") or {}).get("files") or []) + workitems.design_paths(d)
    touched = any(globs.match_any(scopes, p) for p in paths)
    return [(c, src) for c, src in commands if c.get("when_changed") or src == "config" or touched]


def snapshot(repo: str = ".", exclude: str | None = None) -> dict[str, tuple[int, int]]:
    """The modification time and size of every tracked or untracked, not ignored file, except those under `exclude`."""
    names = git.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo).split("\0")
    prefix = exclude.rstrip("/") + "/" if exclude else None
    out: dict[str, tuple[int, int]] = {}
    for name in names:
        if not name or (prefix and name.startswith(prefix)):
            continue
        try:
            st = os.stat(os.path.join(repo, name))
        except OSError:
            continue  # deleted: its absence changes the snapshot
        out[name] = (st.st_mtime_ns, st.st_size)
    return out


def watch_tests(run_once, *, repo: str = ".", interval_seconds: float = 1.0, exclude: str | None = None, sleep=time.sleep, max_runs: int | None = None) -> int:
    """Run `run_once` now and again whenever a file changes, polling every `interval` seconds, until Ctrl-C (exit 0).

    Stdlib only: it compares modification times and sizes, so it needs no file-system events. The snapshot is taken
    again after each run, so a test that rewrites a file (a snapshot, a cache) does not start the next run by itself."""
    last: dict[str, tuple[int, int]] | None = None
    runs = 0
    try:
        while True:
            now = snapshot(repo, exclude)
            if now != last:
                run_once()
                runs += 1
                if max_runs is not None and runs >= max_runs:
                    return 0
                last = snapshot(repo, exclude)
            sleep(interval_seconds)
    except KeyboardInterrupt:
        return 0


def _watch_patterns(spec_path: str | None, declared: dict | None) -> list[str]:
    """What a test run must leave as it was: the config, and the Spec with every file it freezes (its tests, design
    files, frozen docs, and the manifests that hold its frozen sections)."""
    return [config.CONFIG_PATH, *([spec_path, *workitems.frozen_files(declared)] if spec_path and declared else [])]


# What running a test writes on its own beside the tests, never a change to them: Python's bytecode and test caches.
_CACHES = re.compile(r"(^|/)(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache)/|\.py[co]$")


def _snapshot(cwd: str, patterns: list[str]) -> dict[str, str]:
    """Each watched file under `cwd`, tracked or not, with its SHA-256: "gone" for a tracked one that is not there, and
    "unreadable" for one that cannot be read, so either counts as a change."""
    # `-t` tags each file: "?" for one git does not track. Only an untracked cache is skipped; a tracked one stays watched.
    listed = git.run(["ls-files", "-z", "-t", "--cached", "--others", "--exclude-standard"], cwd, check=False, raw=True).split("\0")
    tagged = [(x[:1], x[2:]) for x in listed if len(x) > 2]
    files = {f for tag, f in tagged if not (tag == "?" and _CACHES.search(f)) and globs.match_any(patterns, f)}
    files |= {p for p in patterns if (Path(cwd) / p).is_file()}
    out: dict[str, str] = {}
    for f in sorted(files):
        path = Path(cwd) / f
        try:
            out[f] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "gone"
        except OSError as exc:
            out[f] = f"unreadable ({type(exc).__name__})"
    return out


def _check_untouched(before: dict[str, str], cwd: str, patterns: list[str], when: str) -> None:
    """Fail the run when a command changed, removed, or added a watched file (`_snapshot`): no evidence is written."""
    after = _snapshot(cwd, patterns)
    changed = sorted(f for f in before.keys() | after.keys() if before.get(f) != after.get(f, "gone"))
    if changed:
        shown = ", ".join(changed[:5]) + (f", and {len(changed) - 5} more" if len(changed) > 5 else "")
        raise RuntimeError(
            f"{when} changed {shown}, which a test run must never write: the Spec, its frozen files, or the config. "
            "No evidence was written. Restore them (`git checkout -- <path>`), find what writes them, and run `aidd test` again"
        )


def run_tests(
    *,
    repo: str = ".",
    base: str | None = None,
    spec: str | None = None,
    out_dir: str = config.EVIDENCE_DIR,
    red: bool = True,
    red_in_place: bool = False,
    pass_env: list[str] | tuple[str, ...] = (),
    changed: bool = False,
) -> tuple[dict, list[str]]:
    """Run every applicable command and write evidence.json. Returns (evidence, notes for the author).

    With `changed`, only the commands the working tree's diff against the base selects (`select_changed`), green only,
    and the evidence says `partial`: a quick check between steps, never the change's evidence.

    The commands run without any credential-like variable, except those named in `pass_env`."""
    notes: list[str] = []
    base = base or git.default_base(repo)
    head_sha = git.rev_parse("HEAD", repo)
    base_tip = git.rev_parse(base, repo)
    base_sha = git.merge_base(base_tip, head_sha, repo)
    if red_in_place and (dirty := git.dirty(repo)):
        raise RuntimeError("--red-in-place needs a clean tracked tree before the tests run; dirty: " + ", ".join(dirty[:10]))
    out = Path(out_dir).resolve()
    unclean = dirty_paths(repo, out)
    cfg, declared, spec_path = _declarations(repo, base_sha, head_sha, spec=spec)
    tests = (declared or {}).get("tests") or {}
    patterns = _watch_patterns(spec_path, declared)
    before = _snapshot(repo, patterns)
    paths = working_tree_paths(repo, base_sha) if changed else changed_paths(git.numstat(base_sha, head_sha, repo))
    in_spec_phase = False
    if spec_path and declared is not None and not changed:
        frozen = [spec_path, *tests.get("files", []), *workitems.design_paths(declared), *workitems.threat_models(declared, cfg.docs_dir)]
        in_spec_phase = spec_phase(paths, frozen, [t.get("scope") or [] for t in declared.get("tasks") or []])
    route = (declared or {}).get("route")
    commands, dupes = required_tests(cfg.tests, tests.get("commands", []), "spec", paths, route=route)
    if dupes:
        raise RuntimeError(f"test names declared twice (config and Spec): {', '.join(dupes)}; give each command a unique name")
    if changed:
        commands = select_changed(commands, declared, paths)
        notes.append(f"partial: {len(commands)} command(s) the working tree's changes select, green only; run a full `aidd test` once on the final head")
        notes += weakening.weakening_notes(repo, base_sha)
        red = False
    elif not commands:
        notes.append("no tests apply: the config has no `tests` and the change declares none")
    logs = out / "logs"
    results = []
    for c, src in commands:  # each command is checked on its own, so none can change what the next one reads
        results.append(_run(c, "green", src, repo, logs, pass_env))
        _check_untouched(before, repo, patterns, f"the green run of {c.get('name')}")
    new_behavior = [c for c, _ in commands if c.get("new_behavior")]
    if new_behavior and not red:
        if not changed:  # the partial note already says green only
            notes.append("red skipped (--no-red): the final run must show the new tests fail on the base")
    elif new_behavior and base_sha == head_sha:
        notes.append("red skipped: base and head are the same commit (wrong --base?)")
    elif new_behavior:
        results += _red_runs(repo, base_sha, head_sha, tests, new_behavior, logs, red_in_place, pass_env, patterns)
    notes += junit.report_notes(results)
    evidence: dict = {"aidd_version": __version__, "head_sha": head_sha, "base_sha": base_sha, "runner": _runner(), "results": results}
    if changed:
        evidence["partial"] = True
    if unclean:
        evidence["dirty_tree"] = True
        evidence["dirty_paths"] = unclean[:MAX_DIRTY_PATHS]
        if not changed:  # the partial note already says it is no change's evidence
            shown = ", ".join(unclean[:5]) + (f", and {len(unclean) - 5} more" if len(unclean) > 5 else "")
            notes.append(
                f"dirty tree: the tests ran with uncommitted changes or untracked files ({shown}), so these results prove nothing about "
                "the head commit; commit or stash them, then run `aidd test` again"
            )
    if in_spec_phase:
        evidence["spec_phase"] = True
        notes.append(
            "Spec phase: this branch holds only the Spec and the files it freezes, so its tests failing on head is expected before "
            "Implement. The red and green results stay in the evidence as early proof"
        )
    errs = json_schema.validate(evidence, "evidence.schema.json")
    if errs:
        raise RuntimeError("evidence failed its own schema: " + "; ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence, notes


# The exits pytest gives when no test ran to a failure: an internal error, a usage error, or nothing collected.
PYTEST_NOT_RED = (3, 4, 5)


def runs_pytest(command: object) -> bool:
    """Whether a test command runs pytest: `pytest` or `py.test` as a program, or `-m pytest`, in any wrapper."""
    if not isinstance(command, list):
        return False
    words = [str(w) for w in command]
    progs = [re.split(r"[\\/]", w)[-1].lower().removesuffix(".exe") for w in words]
    return any(p in ("pytest", "py.test") for p in progs) or any(w == "-m" and progs[i + 1 : i + 2] == ["pytest"] for i, w in enumerate(words))


def red_ok(result: dict) -> bool:
    """A red run proves new behavior only when it failed with a real exit code: not a timeout, not a missing command,
    and, for pytest, not an exit that says no test failed (PYTEST_NOT_RED)."""
    code = result.get("exit")
    if result.get("status") != "failed" or code in (None, 126, 127):
        return False
    return not (code in PYTEST_NOT_RED and runs_pytest(result.get("command")))
