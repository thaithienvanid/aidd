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

from . import __version__, gitutil, globs, inputs, model, rules, schema
from . import config as cfgmod
from .localctx import find_spec_in_diff
from .util import kill_group, scrub_credentials, utc_stamp

DEFAULT_TIMEOUT = 1800
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


def execute(command: list[str], *, cwd: str, log: Path, timeout: float, env: dict[str, str] | None = None, pass_env: list[str] | tuple[str, ...] = ()) -> dict:
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
    if env:
        clean_env.update(env)
    with open(log, "wb") as out:
        try:
            proc = subprocess.Popen(command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, env=clean_env, start_new_session=hasattr(os, "killpg"))
        except OSError as exc:
            out.write(f"not started: {exc}\n".encode())
            return {"exit": None, "status": "not_started", "duration_s": 0.0, "started_at": started, "finished_at": utc_stamp()}
        try:
            code = proc.wait(timeout=timeout)
            status = "passed" if code == 0 else "failed"
        except subprocess.TimeoutExpired:
            code, status = None, "timeout"
        # Kill the whole process group every time, so an ordinary background
        # process a test started (a dev server, a watcher) cannot outlive it.
        # This is hygiene, not containment: code that leaves the group (setsid)
        # or an earlier step of the same job can still write anything. The
        # test job runs PR code and is untrusted; evidence is as honest as it.
        kill_group(proc)
        proc.wait()
    if log.exists() and log.stat().st_size > MAX_LOG_BYTES:
        with open(log, "r+b") as fh:
            fh.seek(MAX_LOG_BYTES)
            fh.truncate()
            fh.write(b"\n... [truncated by aidd runner: log exceeded limit] ...\n")
    return {"exit": code, "status": status, "duration_s": round(time.monotonic() - t0, 3), "started_at": started, "finished_at": utc_stamp()}


def load_declarations(repo: str, base_tip: str, head_sha: str, base_sha: str, *, spec: str | None, body: str | None) -> tuple[cfgmod.Config, dict | None, str]:
    """The config in force (base tip, with extends and any org preset) and the change's test declaration."""
    decl = inputs.declared_inputs(repo, base_tip, head_sha, body or "", org_preset=inputs.org_preset_text())
    # The test job runs the change's code anyway, so a bootstrap change may run the suite its own config declares.
    cfg = decl["config"] or decl["bootstrap_config"]
    if cfg is None:
        text = decl["base_config"] or decl["head_files"].get(cfgmod.CONFIG_PATH)
        if text is None:
            raise cfgmod.ConfigError(f"no {cfgmod.CONFIG_PATH} at the base branch or head")
        cfg = cfgmod.load_text(text, prefetched=decl["extends_texts"])  # raises the real error
    declared: dict | None = None
    source = "spec"
    if body:
        cr, errs = model.parse_change_block(body)
        if errs:
            raise model.ModelError("; ".join(errs))
        if cr and "spec" in cr:
            spec = cr["spec"]
        elif cr:
            declared, source = cr, "change_request"
    if declared is None:
        files = gitutil.numstat(base_sha, head_sha, repo)
        spec = inputs.repo_path(spec) if spec else find_spec_in_diff(files, cfg.specs_dir, lambda p: gitutil.show(head_sha, p, repo))
        if spec:
            text = gitutil.show(head_sha, spec, repo)
            if text is None:
                raise model.ModelError(f"{spec} is not in the head commit; commit it first")
            # The Spec names the commands and their log files: it must pass its schema before anything runs.
            declared, _, errs = model.load_object(text, spec)
            if errs:
                raise model.ModelError("; ".join(errs))
    return cfg, declared, source


def _run(c: dict, phase: str, source: str, cwd: str, logs: Path, pass_env: list[str] | tuple[str, ...]) -> dict:
    log = log_path(logs, phase, c["name"])
    r = execute(c["command"], cwd=cwd, log=log, timeout=c.get("timeout_seconds", DEFAULT_TIMEOUT), pass_env=pass_env)
    return {"name": c["name"], "source": source, "command": c["command"], "phase": phase, "log": log.relative_to(logs.parent).as_posix(), **r}


def _materialize(repo: str, head_sha: str, test_files: list[str], dest_root: str) -> None:
    for rel in test_files:
        content = gitutil.show_bytes(head_sha, rel, repo)
        if content is None:
            raise gitutil.GitError(f"{rel} is not in {head_sha[:12]}")
        dest = Path(dest_root) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)


def _red_runs(
    repo: str, base_sha: str, head_sha: str, tests: dict, commands: list[dict], logs: Path, in_place: bool, pass_env: list[str] | tuple[str, ...] = ()
) -> list[dict]:
    test_files = model.tests_files(tests.get("files", []), gitutil.ls_tree(head_sha, repo))
    results: list[dict] = []

    def run_all(cwd: str) -> None:
        _materialize(repo, head_sha, test_files, cwd)
        results.extend(_run(c, "red", "spec", cwd, logs, pass_env) for c in commands)

    if in_place:
        # CI workspaces keep installed dependencies (node_modules, .venv) this way. Tests may have
        # rewritten tracked files (snapshots, lockfiles); a forced checkout discards those edits.
        branch = gitutil.run(["symbolic-ref", "-q", "--short", "HEAD"], repo, check=False).strip()
        try:
            gitutil.run(["checkout", "--quiet", "--force", "--detach", base_sha], repo)
            run_all(repo)
        finally:
            back = ["checkout", "--quiet", "--force", branch] if branch else ["checkout", "--quiet", "--force", "--detach", head_sha]
            gitutil.run(back, repo)
        return results
    tmp = tempfile.mkdtemp(prefix="aidd-red-")
    try:
        gitutil.run(["worktree", "add", "--detach", "--force", tmp, base_sha], repo)
        run_all(tmp)
    finally:
        gitutil.run(["worktree", "remove", "--force", tmp], repo, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def working_tree_paths(repo: str, base_sha: str) -> list[str]:
    """Every path the working tree changes against the base: committed, staged, unstaged, and untracked but not ignored."""
    tracked = gitutil.run(["diff", "--name-only", "--no-renames", "-z", base_sha, "--"], repo).split("\0")
    untracked = gitutil.run(["ls-files", "-z", "--others", "--exclude-standard"], repo).split("\0")
    return sorted({p for p in tracked + untracked if p})


def select_changed(commands: list[tuple[dict, str]], declared: dict | None, paths: list[str]) -> list[tuple[dict, str]]:
    """The commands `aidd test --changed` runs for these working-tree paths.

    A command with `when_changed` runs when it matches (required_tests already checked). A Spec's command without it
    runs when a path is inside a Task's scope or the Spec's test and design files. Any other command applies to every
    path, so it runs whenever something changed."""
    if not paths:
        return []
    d = declared or {}
    scopes = [s for task in d.get("tasks") or [] for s in task.get("scope") or []]
    scopes += list((d.get("tests") or {}).get("files") or []) + list((d.get("design") or {}).get("files") or [])
    touched = any(globs.match_any(scopes, p) for p in paths)
    return [(c, src) for c, src in commands if c.get("when_changed") or src == "config" or touched]


def snapshot(repo: str = ".", exclude: str | None = None) -> dict[str, tuple[int, int]]:
    """The modification time and size of every tracked or untracked, not ignored file, except those under `exclude`."""
    names = gitutil.run(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo).split("\0")
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


def watch(run_once, *, repo: str = ".", interval: float = 1.0, exclude: str | None = None, sleep=time.sleep, max_runs: int | None = None) -> int:
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
            sleep(interval)
    except KeyboardInterrupt:
        return 0


def run_tests(
    *,
    repo: str = ".",
    base: str | None = None,
    spec: str | None = None,
    body: str | None = None,
    out_dir: str = "aidd-evidence",
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
    base = base or inputs.default_base(repo)
    head_sha = gitutil.rev_parse("HEAD", repo)
    base_tip = gitutil.rev_parse(base, repo)
    base_sha = gitutil.merge_base(base_tip, head_sha, repo)
    if red_in_place and (dirty := gitutil.dirty(repo)):
        raise RuntimeError("--red-in-place needs a clean tracked tree before the tests run; dirty: " + ", ".join(dirty[:10]))
    cfg, declared, source = load_declarations(repo, base_tip, head_sha, base_sha, spec=spec, body=body)
    tests = (declared or {}).get("tests") or {}
    paths = working_tree_paths(repo, base_sha) if changed else rules.changed_paths(gitutil.numstat(base_sha, head_sha, repo))
    commands, dupes = rules.required_tests(cfg.get("tests", default=[]), tests.get("commands", []), source, paths)
    if dupes:
        raise RuntimeError(f"test names declared twice (config and Spec): {', '.join(dupes)}; give each command a unique name")
    if changed:
        commands = select_changed(commands, declared, paths)
        notes.append(f"partial: {len(commands)} command(s) the working tree's changes select, green only; the gate needs a full `aidd test`")
        red = False
    elif not commands:
        notes.append("no tests apply: the config has no [[tests]] and the change declares none (characterization)")
    out = Path(out_dir).resolve()
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
    errs = schema.validate(evidence, "evidence.schema.json")
    if errs:
        raise RuntimeError("evidence failed its own schema: " + "; ".join(errs))
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence, notes
