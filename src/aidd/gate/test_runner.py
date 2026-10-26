"""Run the tests and write evidence bound to the head and base commits.

green: every applicable command runs on head.
red:   each new_behavior command runs against the base commit with the head's
       test files copied in. It must fail, which proves the test detects the
       change instead of passing on anything.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from aidd import __version__, config, workitems
from aidd.gate import inputs, routing, rulebook
from aidd.kernel import documents, git, globs, json_schema, processes, repo_paths
from aidd.kernel.processes import scrub_credentials, wait_unreaped
from aidd.kernel.timestamps import utc_stamp

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
    clean_env.setdefault("AIDD_WORKTREE", workitems.worktree_slug(git.toplevel(check=False) or os.getcwd()))
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


def _declarations(
    repo: str, base_tip: str, head_sha: str, base_sha: str, *, spec: str | None, body: str | None
) -> tuple[config.Config, dict | None, str, str | None]:
    """The config in force (base tip, with extends and any org preset), the change's test declaration, its source, and
    the path of the Spec it read (None for an inline Change Request block or no declaration)."""
    if body is None:
        # Locally, the Change Request block a branch commit carries (`aidd describe --commit`), as a PR/MR description would.
        body = inputs.commit_block(repo, base_sha, head_sha)
    decl = inputs.declared_inputs(repo, base_tip, head_sha, body or "", org_preset=config.org_preset_text())
    # The test job runs the change's code anyway, so a bootstrap change may run the suite its own config declares.
    cfg = decl["config"] or decl["bootstrap_config"]
    if cfg is None:
        text = decl["base_config"] or decl["head_files"].get(config.CONFIG_PATH)
        if text is None:
            raise config.ConfigError(f"no {config.CONFIG_PATH} at the base branch or head")
        cfg = config.load_text(text, prefetched=decl["extends_texts"])  # raises the real error
    declared: dict | None = None
    source = "spec"
    if body:
        cr, errs = workitems.parse_change_block(body)
        if errs:
            raise documents.DocumentError("; ".join(errs))
        if cr and "spec" in cr:
            spec = cr["spec"]
        elif cr and "specs" in cr:
            return cfg, _goal_tests(repo, head_sha, list(cr["specs"])), "spec", None
        elif cr:
            declared, source = cr, "change_request"
    if declared is None:
        files = git.numstat(base_sha, head_sha, repo)
        found = [repo_paths.repo_path(spec)] if spec else workitems.find_specs_in_diff(files, cfg.specs_dir, lambda p: git.show(head_sha, p, repo))
        on_goal = git.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip().startswith(workitems.GOAL_PREFIX)
        if found and on_goal:  # a goal's Specs, one or more, each judged as its own change
            return cfg, _goal_tests(repo, head_sha, found), "spec", None
        spec = found[0] if len(found) == 1 else None
        if spec:
            text = git.show(head_sha, spec, repo)
            if text is None:
                raise documents.DocumentError(f"{spec} is not in the head commit; commit it first")
            # The Spec names the commands and their log files: it must pass its schema before anything runs.
            declared, _, errs = workitems.load_object(text, spec)
            if errs:
                raise documents.DocumentError("; ".join(errs))
    return cfg, declared, source, spec if source == "spec" and declared is not None else None


def _goal_tests(repo: str, head_sha: str, specs: list[str]) -> dict:
    """A goal's test declaration: every command and test file its Specs name, so one run proves each of them. Each
    command is named for its Spec (workitems.goal_command), as the gate reads it."""
    commands: list[dict] = []
    files: list[str] = []
    for path in specs:
        text = git.show(head_sha, path, repo)
        if text is None:
            raise documents.DocumentError(f"{path} is not in the head commit; commit it first")
        data, _, errs = workitems.load_object(text, path)
        if errs:
            raise documents.DocumentError("; ".join(errs))
        tests = data.get("tests") or {}
        commands += [workitems.goal_command(str(data["id"]), c) for c in tests.get("commands") or []]
        files += [f for f in tests.get("files") or [] if f not in files]
    return {"tests": {"commands": commands, "files": files}}


def _run(c: dict, phase: str, source: str, cwd: str, logs: Path, pass_env: list[str] | tuple[str, ...]) -> dict:
    """One command's result. On head, a failure is tried again up to its `retries`: every attempt is kept, and a pass
    after a failure is marked flaky. A red run on the base commit is tried once: a retry could turn a flaky test red."""
    retries = int(c.get("retries", 0) or 0) if phase == "green" else 0
    attempts: list[dict] = []
    for i in range(retries + 1):
        log = log_path(logs, phase, c["name"] if i == 0 else f"{c['name']}.attempt-{i + 1}")
        r = run_test_command(c["command"], cwd=cwd, log=log, timeout_seconds=c.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS), pass_env=pass_env)
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
    repo: str, base_sha: str, head_sha: str, tests: dict, commands: list[dict], logs: Path, in_place: bool, pass_env: list[str] | tuple[str, ...] = ()
) -> list[dict]:
    test_files = workitems.tests_files(tests.get("files", []), git.ls_tree(head_sha, repo))
    results: list[dict] = []

    def run_all(cwd: str) -> None:
        _materialize(repo, head_sha, test_files, cwd)
        results.extend(_run(c, "red", "spec", cwd, logs, pass_env) for c in commands)

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


def run_tests(
    *,
    repo: str = ".",
    base: str | None = None,
    spec: str | None = None,
    body: str | None = None,
    out_dir: str = config.EVIDENCE_DIR,
    red: bool = True,
    red_in_place: bool = False,
    pass_env: list[str] | tuple[str, ...] = (),
    changed: bool = False,
) -> tuple[dict, list[str]]:
    """Run every applicable command and write evidence.json. Returns (evidence, notes for the author).

    With `changed`, only the commands the working tree's diff against the base selects (`select_changed`), green only,
    and the evidence says `partial`: a local convenience the gate never accepts as the change's evidence.

    The commands run without SECRET_ENV and without any credential-like variable, except those named in `pass_env`."""
    notes: list[str] = []
    base = base or git.default_base(repo)
    head_sha = git.rev_parse("HEAD", repo)
    base_tip = git.rev_parse(base, repo)
    base_sha = git.merge_base(base_tip, head_sha, repo)
    if red_in_place and (dirty := git.dirty(repo)):
        raise RuntimeError("--red-in-place needs a clean tracked tree before the tests run; dirty: " + ", ".join(dirty[:10]))
    out = Path(out_dir).resolve()
    unclean = dirty_paths(repo, out)
    cfg, declared, source, spec_path = _declarations(repo, base_tip, head_sha, base_sha, spec=spec, body=body)
    tests = (declared or {}).get("tests") or {}
    paths = working_tree_paths(repo, base_sha) if changed else routing.changed_paths(git.numstat(base_sha, head_sha, repo))
    in_spec_phase = False
    if spec_path and declared is not None and not changed:
        frozen = [spec_path, *tests.get("files", []), *workitems.design_paths(declared), *workitems.threat_models(declared, cfg.docs_dir)]
        in_spec_phase = routing.spec_phase(paths, frozen, [t.get("scope") or [] for t in declared.get("tasks") or []])
    route = (declared or {}).get("route") if source == "change_request" else None
    commands, dupes = routing.required_tests(cfg.get("tests", default=[]), tests.get("commands", []), source, paths, route=route)
    if dupes:
        raise RuntimeError(f"test names declared twice (config and Spec): {', '.join(dupes)}; give each command a unique name")
    if changed:
        commands = select_changed(commands, declared, paths)
        notes.append(f"partial: {len(commands)} command(s) the working tree's changes select, green only; the gate needs a full `aidd test`")
        red = False
    elif not commands:
        notes.append("no tests apply: the config has no `tests` and the change declares none (characterization)")
    logs = out / "logs"
    results = [_run(c, "green", src, repo, logs, pass_env) for c, src in commands]
    new_behavior = [c for c, _ in commands if c.get("new_behavior")]
    if new_behavior and not red:
        if not changed:  # the partial note already says green only
            notes.append("red skipped (--no-red): the gate will require it")
    elif new_behavior and base_sha == head_sha:
        notes.append("red skipped: base and head are the same commit (wrong --base?)")
    elif new_behavior:
        results += _red_runs(repo, base_sha, head_sha, tests, new_behavior, logs, red_in_place, pass_env)
    evidence: dict = {"aidd_version": __version__, "head_sha": head_sha, "base_sha": base_sha, "runner": _runner(), "results": results}
    if changed:
        evidence["partial"] = True
    if unclean:
        evidence["dirty_tree"] = True
        evidence["dirty_paths"] = unclean[:MAX_DIRTY_PATHS]
        if not changed:  # the partial note already says the gate takes none of it
            shown = ", ".join(unclean[:5]) + (f", and {len(unclean) - 5} more" if len(unclean) > 5 else "")
            notes.append(
                f"dirty tree: the tests ran with uncommitted changes or untracked files ({shown}), so the gate counts none of these "
                f"results; {rulebook.BY_NAME['tests'].fix_for('tests.dirty_tree')}"
            )
    if in_spec_phase:
        evidence["spec_phase"] = True
        notes.append(
            "Spec phase: this branch holds only the Spec and the files it freezes, so its tests failing on head is expected before "
            "Implement. The red and green results stay in the evidence as early proof, and the gate waits for Spec approval"
        )
    errs = json_schema.validate(evidence, "evidence.schema.json")
    if errs:
        raise RuntimeError("evidence failed its own schema: " + "; ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence, notes
