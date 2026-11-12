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
from collections.abc import Callable
from pathlib import Path

from aidd import __version__, config, workitems
from aidd.kernel import documents, git, git_reads, globs, json_schema, processes, resources
from aidd.kernel.processes import scrub_credentials, wait_unreaped
from aidd.kernel.regular_files import MISSING, REPOSITORY_FILE_MODE, from_root, link_on_the_way, named_file_bytes, open_for_write
from aidd.kernel.timestamps import utc_stamp
from aidd.testing import base_frozen, base_view, governing, junit, related_tests, target_view

MAX_LOG_BYTES = 10 * 1024 * 1024
CI_RUNNER_ENV = ("GITHUB_ACTIONS", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITLAB_CI", "CI_JOB_ID", "CI_JOB_URL")


def _tool_versions() -> dict:
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
    if os.path.islink(log) or os.path.islink(logs):
        raise RuntimeError(f"{log if os.path.islink(log) else logs} is a link, and `aidd test` writes no log through a link: remove it, then run `aidd test`")
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
    clean_env.setdefault("AIDD_WORKTREE", worktree_slug(git.repository_top() or os.getcwd()))
    if env:
        clean_env.update(env)
    with open_for_write(log) as out:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=clean_env, start_new_session=hasattr(os, "killpg"))
        except OSError as exc:
            out.write(f"not started: {exc}\n".encode())
            return {"exit": None, "status": "not_started", "duration_seconds": 0.0, "started_at": started, "finished_at": utc_stamp()}
        try:
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
        finally:
            git_reads.forget_reads()  # the test command may have written the repository, and a scope sees only aidd's own git calls
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


def before_implement(paths: list[str], frozen: list[str], task_scopes: list[list[str]], statuses: list[str]) -> bool:
    """Whether a Spec-backed change is still in the Design stage, before Implement. The stored status of every governing
    Spec is before Implement (`BEFORE_IMPLEMENT`), and the paths agree: each changed path is a Spec or a file it freezes,
    and some Task's scope has no change yet. Its tests are expected to fail on head until Implement."""
    if not statuses or not all(s in workitems.BEFORE_IMPLEMENT for s in statuses):
        return False
    if not paths or not all(globs.match_any(frozen, p) for p in paths):
        return False
    return any(scope and not any(globs.match_any(scope, p) for p in paths) for scope in task_scopes)


def required_tests(
    config_tests: list[dict], declared: list[dict], paths: list[str], route: str | None = None, base: base_view.BaseTests | None = None
) -> tuple[list[tuple[dict, str]], list[str]]:
    """The (command, source) pairs this diff must run, and any names declared twice. On the emergency route the
    repository suite is its `smoke: true` commands when it marks any (`base_view.emergency_subset`: the base decides which),
    and the change's own commands add to them. The base's copies of tests the head changed are the exception: the head's route
    never drops one, since the head chooses the route."""
    if route == "emergency":
        config_tests = base_view.emergency_subset(config_tests, base)
    pairs = [(c, "config") for c in config_tests] + [(c, "config") for c in (base.copies if base else [])] + [(c, "spec") for c in declared]
    names = [c["name"] for c, _ in pairs]
    dupes = sorted({n for i, n in enumerate(names) if n in names[:i]})
    selected = select_tests([c for c, _ in pairs], paths)
    return [(c, src) for c, src in pairs if any(c is s for s in selected)], dupes


def _load_config(repo: str, read_old_shape: bool = False) -> config.Config:
    path = Path(repo) / config.CONFIG_PATH
    if not path.is_file():
        raise config.ConfigError(f"no {config.CONFIG_PATH} here; `aidd init` writes one")
    if not read_old_shape:
        return config.load_or_stop(config.CONFIG_PATH, repo)
    at = git.rev_parse("HEAD", repo)  # a commit the change does not control: read as the base's is, in today's shape
    cfg, _ = base_view.load_config(repo, at)
    if cfg is None:
        raise RuntimeError(
            f"the {config.CONFIG_PATH} at {at[:12]} does not load, even read in today's shape, so the tests there cannot run again. "
            "Run `aidd validate` there to see why, or approve the Spec again on a commit whose config loads"
        )
    return cfg


def _design_specs(specs: list[governing.Governing], docs_dir: str, paths: list[str]) -> set[int]:
    """The Specs (by index) whose own failing runs are expected, each judged alone by `before_implement`: its stored status is
    before Implement, and the paths are its own file and the files it freezes. One Spec's frozen list never excuses another's."""
    designed = set()
    for i, g in enumerate(specs):
        tests = g.data.get("tests") or {}
        frozen = [g.path, *tests.get("files", []), *workitems.design_paths(g.data), *workitems.threat_models(g.data, docs_dir)]
        scopes = [t.get("scope") or [] for t in g.data.get("tasks") or []]
        if g.why != "base" and before_implement(paths, frozen, scopes, [workitems.spec_status(g.data)]):
            designed.add(i)
    return designed


BASE = "base"  # the owner of a command copied from the base commit's config


def _declared(specs: list[governing.Governing], config_tests: list[dict], base_tests: list[dict]) -> tuple[list[dict], dict[int, int | str | None]]:
    """Every command the governing Specs declare, and who each command belongs to, by identity: its Spec's index, None for
    the head's config, or BASE. With several Specs each command is named `<Spec id>.<name>`, since two may name one `acceptance`."""
    declared: list[dict] = []
    owner: dict[int, int | str | None] = {**{id(c): None for c in config_tests}, **{id(c): BASE for c in base_tests}}
    for i, g in enumerate(specs):
        for c in (g.data.get("tests") or {}).get("commands", []):
            mine = {**c, "name": f"{g.data['id']}.{c['name']}"} if len(specs) > 1 else c
            declared.append(mine)
            owner[id(mine)] = i
    return declared, owner


def _nothing_ran(configured: bool, declared: bool, paths: list[str]) -> str:
    """The note for a full run that selected no command, and the step that works. Nothing configured, or an applying Spec whose
    commands were all skipped, exits 1. Commands that exist but none of which covers the changed paths is the project's own
    declared state: exit 0, with no test applied."""
    if not configured and not declared:
        return (
            "nothing ran, so nothing here proves the change, and `aidd test` exits 1: the config has no `tests` and no Spec for this change declares any. "
            f"Ask the person to add the project's test command under `tests:` in {config.CONFIG_PATH}, or write the change's tests in a Spec "
            "(`tests.commands`), then run `aidd test` again"
        )
    if declared:
        return (
            "nothing ran, so nothing here proves the change, and `aidd test` exits 1: a Spec for this change declares commands, and each is limited by "
            f"`when_changed` to paths this change does not touch ({len(paths)} changed). Fix the Spec's `when_changed`, or ask for `spec.revise`; "
            "or add a command with no `when_changed`, then run `aidd test` again"
        )
    return (
        f"no test applied to this change: every test command is limited by `when_changed`, and none matches its {len(paths)} changed path(s), "
        "so `aidd test` exits 0 and shows nothing proven. To check every change, add one command with no `when_changed`, such as a lint"
    )


def _plan(cfg: config.Config, base_cfg: config.Config | None, specs: list[governing.Governing], paths: list[str]):
    """The commands this diff must run, from the head's config, the base's view of it (`base_view`), and the Specs that apply:
    the commands, who owns each, the names declared twice, the Spec commands, the base's copies, a note for them, and whether the
    emergency route cut the repository suite to its smoke set. One
    decision for `run_tests` and `tests_apply`, so a merge check and a run never differ."""
    base_held, notes = base_view.base_tests(base_cfg, cfg.tests)
    base_tests = base_held.copies if base_held else []
    config_tests = cfg.tests
    declared, owner = _declared(specs, config_tests, base_tests)
    routes = {g.data.get("route") for g in specs}
    route = routes.pop() if len(routes) == 1 else None
    commands, dupes = required_tests(config_tests, declared, paths, route=route, base=base_held)
    # The suite ran as its smoke set: the route is emergency and that dropped a command of it. The evidence says so (`emergency_subset`).
    cut = route == "emergency" and len(base_view.emergency_subset(config_tests, base_held)) < len(config_tests)
    return commands, dupes, declared, owner, bool(config_tests or base_tests), notes, cut


def tests_apply(repo: str, head_sha: str, base_sha: str) -> bool:
    """Whether any test command applies to the change from `base_sha` to `head_sha`: the decision `run_tests` makes, from the head's
    committed config, the base's view, the Specs that apply, and `when_changed` against the diff, with nothing run. False for a
    change no command covers, which no test could show works. True when the config or a Spec does not load, so the check that reads
    it defers on its own."""
    text = git.show(head_sha, config.CONFIG_PATH, repo)
    if text is None:
        return True
    try:
        cfg = config.load_text(text, read=lambda p: git.show(head_sha, p, repo), root_preset=config.org_preset_text(), skip_unread=True)
        base_cfg, _ = base_view.load_config(repo, base_sha)
        files = git.numstat(base_sha, head_sha, repo)
        paths = changed_paths(files)
        found, _ = governing.find_governing(repo, cfg.specs_dir, head_sha, governing.GoverningChange(files, paths, "", None, base_sha))
        commands = _plan(cfg, base_cfg, [g for g in found if g.runs], paths)[0]
    except (config.ConfigError, documents.DocumentError, git.GitError):
        return True
    return bool(commands)


def command_folder(top: str, command: dict) -> str:
    """The folder `command` runs in: `top`, the tree being tested, or its `runs_in` folder inside it. A folder outside
    the tree, or reached through a link, would run a command where nothing was tested, so it is refused and nothing runs. The tree
    is the head's or the base's own checkout, so each run checks the folder again."""
    rel = command.get("runs_in")
    if not rel:
        return top
    if bad := link_on_the_way(Path(top).absolute(), rel):
        raise RuntimeError(
            f"test command {command.get('name')} runs in {rel}, and `{bad}` is a link or lies outside the repository, so `aidd test` ran no command and wrote no evidence. "
            "Name a folder inside the repository that no link leads through in `runs_in`, then run `aidd test` again"
        )
    return str(Path(top) / rel)


def _run(c: dict, phase: str, source: str, cwd: str, logs: Path, pass_env: list[str] | tuple[str, ...]) -> dict:
    """One command's result. On head, a failure is run again up to its `reruns`: every attempt is kept, and a pass
    after a failure is marked flaky. A red run on the base commit is run once: a rerun could turn a flaky test red. The
    command runs in its `runs_in` folder (`command_folder`); its `report` stays a path from `cwd`, the top of the tree."""
    where = command_folder(cwd, c)
    reruns = int(c.get("reruns", config.setting_default("tests.reruns")) or 0) if phase == "green" else 0
    attempts: list[dict] = []
    report = c.get("report")
    for i in range(reruns + 1):
        log = log_path(logs, phase, c["name"] if i == 0 else f"{c['name']}.attempt-{i + 1}")
        before = junit.stamp(Path(cwd), report) if report else None
        r = run_test_command(
            c["command"], cwd=where, log=log, timeout_seconds=c.get("timeout_seconds", config.setting_default("tests.timeout_seconds")), pass_env=pass_env
        )
        if report:  # read where the command ran: a red run's tree is gone afterwards
            r["report"] = junit.read_report(Path(cwd), report, before)
        attempts.append({"log": log.relative_to(logs.parent).as_posix(), **r})
        if r["status"] == "passed":
            break
    out = {
        "name": c["name"],
        "source": source,
        "command": c["command"],
        **({"runs_in": c["runs_in"]} if c.get("runs_in") else {}),
        "red_green": phase,
        **attempts[-1],
    }
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
        with open_for_write(dest, root=Path(dest_root), mode=REPOSITORY_FILE_MODE) as out:  # never through a link, even one inside
            out.write(content)


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
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    say = progress or (lambda line: None)
    test_files = workitems.tests_files(tests.get("files", []), git.ls_tree(head_sha, repo))
    results: list[dict] = []

    def run_all(cwd: str) -> None:
        _materialize(repo, head_sha, test_files, cwd)
        # Checked here, in the red tree, before an in-place run's forced checkout would discard what a command wrote.
        before = _first_snapshot(cwd, patterns or [])
        for i, c in enumerate(commands, 1):
            say(f"running {c['name']} on base ({i} of {len(commands)})")
            results.append(_run(c, "red", "spec", cwd, logs, pass_env))
            _check_untouched(before, cwd, patterns or [], f"the red run of {c.get('name')}")

    if in_place:
        # CI workspaces keep installed dependencies (node_modules, .venv) this way. Tests may have
        # rewritten tracked files (snapshots, lockfiles); a forced checkout discards those edits.
        branch = git.current_branch(repo)
        say(f"checking out base {base_sha[:12]} in this checkout for the red runs, then back to {branch or head_sha[:12]}")
        try:
            git.run(["checkout", "--quiet", "--force", "--detach", base_sha], repo)
            run_all(repo)
        finally:
            back = ["checkout", "--quiet", "--force", branch] if branch else ["checkout", "--quiet", "--force", "--detach", head_sha]
            git.run(back, repo)
        return results
    say(f"checking out base {base_sha[:12]} in a separate worktree for the red runs")
    tmp = tempfile.mkdtemp(prefix="aidd-red-")
    try:
        git.run(["worktree", "add", "--detach", "--force", tmp, base_sha], repo)
        run_all(tmp)
    finally:
        git.run(["worktree", "remove", "--force", tmp], repo, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    return results


REVISED_FROZEN = "evidence.schema.json#/properties/revised_frozen"  # the evidence names this many Specs
REVISED_FROZEN_FILES = f"{REVISED_FROZEN}/items/properties/files"  # and this many files of each, the first sorted
DIRTY_PATHS = "evidence.schema.json#/properties/dirty_paths"  # the evidence names this many paths; `dirty_tree` says there were any


def dirty_paths(repo: str, out: Path) -> list[str]:
    """What the tree holds that its head commit does not, so tests run in it prove nothing about that commit: tracked
    changes, staged or not, untracked files the repository's .gitignore files do not ignore, and files git is told not
    to look at (`--assume-unchanged`, or `--skip-worktree` on a file that is there). `.git/info/exclude` and a person's
    global excludes never hide a file, because CI reads neither. `aidd test`'s own output folder is left out."""
    top = Path(git.repository_top(repo) or repo).resolve()
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


def select_changed(commands: list[tuple[dict, str]], declared: dict | list[dict] | None, paths: list[str]) -> list[tuple[dict, str]]:
    """The commands `aidd test --changed` runs for these working-tree paths.

    A command with `when_changed` runs when it matches (required_tests already checked). A Spec's command without it
    runs when a path is inside a Task's scope or the Spec's test files, design files, and frozen docs. Any other command applies to every
    path, so it runs whenever something changed."""
    if not paths:
        return []
    scopes = []
    for d in [declared] if isinstance(declared, dict) else declared or []:
        scopes += [s for task in d.get("tasks") or [] for s in task.get("scope") or []]
        scopes += list((d.get("tests") or {}).get("files") or []) + workitems.design_paths(d)
    touched = any(globs.match_any(scopes, p) for p in paths)
    return [(c, src) for c, src in commands if c.get("when_changed") or src == "config" or touched]


def _watch_patterns(specs: list[governing.Governing]) -> list[str]:
    """What a test run must leave as it was: the config, and each Spec with every file it freezes (its tests, design
    files, frozen docs, and the manifests that hold its frozen sections)."""
    return [config.CONFIG_PATH, *(p for g in specs for p in (g.path, *workitems.frozen_files(g.data)))]


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
        raw, why = named_file_bytes(Path(cwd), f, MAX_WATCHED_BYTES)
        if raw is not None and len(raw) <= MAX_WATCHED_BYTES:
            out[f] = hashlib.sha256(raw).hexdigest()
        else:
            out[f] = "gone" if why == MISSING or not os.path.lexists(Path(cwd) / f) else f"unreadable ({why})"
    return out


# The most of one watched file the runner hashes; a larger one, a link, a pipe, or a device reads as unreadable.
MAX_WATCHED_BYTES = 64 * 1024 * 1024


def _first_snapshot(cwd: str, patterns: list[str]) -> dict[str, str]:
    """`_snapshot` before any command runs. A watched file the reader refuses, such as a link, a pipe, or one past the
    cap, stops the run here: its hash would read the same whatever a command did to what it stands for."""
    before = _snapshot(cwd, patterns)
    refused = sorted(f for f, digest in before.items() if digest.startswith("unreadable"))
    if refused:
        shown = ", ".join(f"{f} ({before[f].removeprefix('unreadable (').removesuffix(')')})" for f in refused[:5])
        raise RuntimeError(
            f"`aidd test` ran no command and wrote no evidence, because it cannot read {shown}, and it checks those files for a change. "
            "Replace each with a regular file under 64 MB, then run `aidd test` again"
        )
    return before


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


def _refuse_links(top: Path, out_dir: str) -> None:
    """`aidd test` writes the evidence and each log through no link: a repository can commit one, and a write through it would
    overwrite a file outside the folder. The folder, its evidence.json, and its logs folder are checked before anything runs;
    each log is opened without following a link."""
    out = Path(os.path.abspath(out_dir))
    for target in (out, out / "evidence.json", out / "logs"):
        inside = from_root(top, target) is not None  # a folder outside the repository (--out) is checked at its own name only
        link = (link_on_the_way(top, target) if inside else "") or (str(target) if os.path.islink(target) else "")
        if link:
            raise RuntimeError(
                f"{link} is a link, and `aidd test` writes no evidence through a link, which could overwrite another file. Remove the link, or pass --out a folder with none"
            )


@git_reads.shared_reads()
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
    progress: Callable[[str], None] | None = None,
    require_green: bool = False,
    read_old_shape: bool = False,
) -> tuple[dict, list[str]]:
    """Run every applicable command and write evidence.json. Returns (evidence, notes for the author).

    With `require_green`, a failing test is a failure even before Implement: a run that gates a merge excuses nothing, and
    the evidence says so. Without it, a Spec still before Implement expects its own tests to fail (the Design stage).

    `progress` hears one line as each command starts, and one before the checkout of the base for the red runs; a caller
    that passes none hears nothing.

    With `changed`, only the commands the working tree's diff against the base selects (`select_changed`), green only,
    and the evidence says `partial`: a quick check between steps, never the change's evidence. A config command with
    `related_tests` then runs only its related tests where the runner sees every change (`related_tests.related_tests_command`), and its
    result says so. A run with `require_green` is never `changed`, so nothing that gates narrows.

    With `read_old_shape`, the head is a commit the change does not control (the one a Spec's approval covers), so its config and
    Specs read in today's shape, as the base's do. The head of a change is read as it is.

    The commands run without any credential-like variable, except those named in `pass_env`."""
    if changed and require_green:  # a partial run skips the red runs and the frozen-file check, so it is never evidence that gates a merge
        raise ValueError("--require-green needs the full run: drop --changed")
    notes: list[str] = []
    say = progress or (lambda line: None)
    base = base or git.default_base(repo)
    head_sha = git.rev_parse("HEAD", repo)
    base_tip = git.rev_parse(base, repo)
    try:
        base_sha = git.merge_base(base_tip, head_sha, repo)
    except git.GitError:
        raise RuntimeError(
            f"this branch and {base} share no commit, so aidd cannot tell what this branch changed: pass --base a branch this one grew from, "
            "or start the branch from the base"
        ) from None
    if red_in_place and (dirty := git.dirty(repo)):
        raise RuntimeError("--red-in-place needs a clean tracked tree before the tests run; dirty: " + ", ".join(dirty[:10]))
    _refuse_links(Path(git.repository_top(repo) or repo), out_dir)
    out = Path(out_dir).resolve()
    unclean = dirty_paths(repo, out)
    cfg = _load_config(repo, read_old_shape)
    files = git.numstat(base_sha, head_sha, repo)
    paths = working_tree_paths(repo, base_sha) if changed else changed_paths(files)
    base_cfg, base_cfg_notes = base_view.load_config(repo, base_sha)
    if base_cfg_notes and require_green:  # the base decides, and a base that cannot be read passes nothing on the head's word
        raise RuntimeError(f"`aidd test` ran no command and wrote no evidence: {base_cfg_notes[0]}")
    notes += base_cfg_notes + base_view.config_notes(cfg, base_cfg)
    found, spec_notes = governing.find_governing(
        repo, cfg.specs_dir, head_sha, governing.GoverningChange(files, paths, governing.change_branch(repo), spec, base_sha, read_old_shape)
    )
    notes += spec_notes
    specs = [g for g in found if g.runs]
    held = {str(g.data.get("id")): g.head for g in specs}
    frozen, revised, revised_frozen = ("", [], []) if changed else base_frozen.base_frozen_problem(repo, cfg.specs_dir, (base_sha, head_sha), paths, held)
    notes += revised
    if frozen:
        if require_green:  # a run that gates a merge passes no change to a file a Spec froze, unless the change revises that Spec
            raise RuntimeError(f"`aidd test` ran no command and wrote no evidence. {frozen}")
        notes.append(f"{frozen} A run that gates a merge (--require-green) fails on this")
    moved = target_view.moved(repo, base_tip, base_sha, base_cfg, specs)  # the target's tip is the local ref `--base` resolved: no network call
    notes += [target_view.note(base, base_sha, moved)] if moved else []
    patterns = _watch_patterns(specs)
    before = _first_snapshot(repo, patterns)
    designed = set() if changed else _design_specs(specs, base_view.docs_dir(cfg, base_cfg), paths)
    excuse = bool(designed) and not require_green
    suite_excused = excuse and len(designed) == len(specs)  # the repository suite sweeps in every Spec's tests, so it is excused only when each Spec is
    commands, dupes, declared, owner, configured, base_notes, emergency_cut = _plan(cfg, base_cfg, specs, paths)
    notes += base_notes
    if dupes:
        raise RuntimeError(f"test names declared twice (config and Spec): {', '.join(dupes)}; give each command a unique name")
    narrowed: dict[int, list[str]] = {}
    if changed:
        commands = select_changed(commands, [g.data for g in specs], paths)
        notes.append(f"partial: {len(commands)} command(s) the working tree's changes select, green only; run a full `aidd test` once on the final head")
        red = False
        narrowed, narrow_notes = related_tests.narrowed_commands(commands, paths, base_sha, git.repository_top(repo) or repo)
        notes += narrow_notes
    elif not commands:
        notes.append(_nothing_ran(configured, bool(declared), paths))
    for c, _ in commands:
        command_folder(repo, c)  # a folder outside the repository or through a link stops the run before any command runs
    logs = out / "logs"
    results = []
    for place, (c, src) in enumerate(commands, 1):  # each command is checked on its own, so none can change what the next one reads
        related = narrowed.get(id(c))
        say(f"running {c['name']} on head ({place} of {len(commands)}){', only its related tests' if related else ''}")
        results.append(_run({**c, "command": related} if related else c, "green", src, repo, logs, pass_env))
        if related:
            results[-1]["related_tests"] = True  # the result shows the command that ran, and says it was not the full one
        who = owner.get(id(c))
        if results[-1]["status"] != "passed" and excuse and (who in designed if isinstance(who, int) else who is None and suite_excused):
            results[-1]["before_implement"] = True  # expected before Implement, for the Spec that owns it; a base command never is
        _check_untouched(before, repo, patterns, f"the green run of {c.get('name')}")
    new_behavior = [c for c, _ in commands if c.get("new_behavior")]
    if new_behavior and not red:
        if not changed:  # the partial note already says green only
            notes.append("red skipped (--no-red): the final run must show the new tests fail on the base")
    elif new_behavior and base_sha == head_sha:
        notes.append("red skipped: base and head are the same commit (wrong --base?)")
    elif new_behavior:
        for i, g in [(None, None), *enumerate(specs)]:  # the config's commands have no Spec's test files to bring to the base
            mine = [c for c in new_behavior if owner.get(id(c)) == i and (g is None or g.red)]
            if mine:
                results += _red_runs(repo, base_sha, head_sha, (g.data.get("tests") or {}) if g else {}, mine, logs, red_in_place, pass_env, patterns, progress)
    notes += junit.report_notes(results)
    evidence: dict = {"aidd_version": __version__, "head_sha": head_sha, "base_sha": base_sha, "runner": _tool_versions(), "results": results}
    evidence["specs"] = [g.path for g in specs]
    evidence["specs_not_run"] = [g.path for g in found if not g.runs]
    if revised_frozen:
        files_cap = json_schema.keyword_at(REVISED_FROZEN_FILES, "maxItems")
        evidence["revised_frozen"] = [{**r, "files": r["files"][:files_cap]} for r in revised_frozen[: json_schema.keyword_at(REVISED_FROZEN, "maxItems")]]
    if emergency_cut:
        evidence["emergency_subset"] = True
    if require_green:
        evidence["require_green"] = True
    if moved:
        evidence["target_moved"] = moved
    if not commands and not changed and configured and not declared:
        evidence["untested"] = True
    if aidd_commit := resources.running_commit():  # an unreleased aidd says this version too, so its commit names it
        evidence["aidd_commit"] = aidd_commit
    if changed:
        evidence["partial"] = True
    elif not red:
        evidence["no_red"] = True  # the exit code of a quick check in a dirty tree differs, so the evidence says it was one
    if unclean:
        evidence["dirty_tree"] = True
        evidence["dirty_paths"] = unclean[: json_schema.keyword_at(DIRTY_PATHS, "maxItems")]
        if not changed:  # the partial note already says it is no change's evidence
            shown = ", ".join(unclean[:5]) + (f", and {len(unclean) - 5} more" if len(unclean) > 5 else "")
            exits = "this full run exits 1 whatever its results say, because it " if red else "the tests "
            notes.append(
                f"dirty tree: {exits}ran with uncommitted changes or untracked files ({shown}), so these results prove nothing about "
                "the head commit; commit or stash them, then run `aidd test` again"
            )
    if any(r.get("before_implement") for r in results):
        evidence["before_implement"] = True
        also_fails = any(r["red_green"] == "green" and r["status"] != "passed" and not r.get("before_implement") for r in results)
        notes.append(
            "Design stage: this branch holds only the Spec and the files it freezes, so its tests failing on head is expected before "
            "Implement. The red and green results stay in the evidence as early proof"
            if not also_fails
            else "Design stage: a Spec's tests failing on head is expected before Implement, but another result failed too, so this run exits 1"
        )
    elif designed and any(r["red_green"] == "green" and r["status"] != "passed" for r in results):
        notes.append(
            "Design stage: this change holds only the Spec and the files it freezes, so its tests failing is expected before Implement. "
            "This run excuses nothing (--require-green), so it exits 1 until Implement makes them pass"
        )
    errs = json_schema.validate(evidence, "evidence.schema.json")
    if errs:
        raise RuntimeError("evidence failed its own schema: " + "; ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    with open_for_write(out / "evidence.json", text=True) as written:
        written.write(json.dumps(evidence, indent=2) + "\n")
    return evidence, notes


# An exit that says the command did not start, as a shell gives it: it cannot run, or it is not found.
NOT_STARTED_EXITS = (126, 127)


def red_ok(result: dict) -> bool:
    """A red run proves new behavior only when it failed with a real exit code: not a timeout, not a missing command, and not
    an exit the runner's own documentation gives for a run in which no test failed (`schemas/test-runners.json`)."""
    code = result.get("exit")
    if result.get("status") != "failed" or code in (None, *NOT_STARTED_EXITS):
        return False
    return not config.no_test_failed_exit(result.get("command"), code)
