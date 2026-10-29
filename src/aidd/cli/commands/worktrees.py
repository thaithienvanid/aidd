"""`aidd worktrees`: every worktree of the repository, what it holds, and its state (workitems/worktree_states.py);
`aidd worktrees clean`: removes the ones that are missing or merged, after a person's yes."""

from __future__ import annotations

import json
import os
import sys

from aidd import config, platforms, workitems
from aidd.cli import arguments
from aidd.kernel import git, processes

# How long one worktree's teardown may run before it is stopped, with its children.
TEARDOWN_SECONDS = 120

# What a removed folder takes with it that git cannot see: a coding agent lists its saved sessions by the folder they
# started in.
SESSIONS_NOTE = (
    "A coding agent lists its saved sessions by folder, so a removed worktree's sessions stop showing when you resume. "
    "They stay on disk, and a worktree added back at the same path shows them again."
)


def cmd_worktrees(args) -> int:
    arguments.enter_repo(args)
    cfg = arguments.config_or_none_quiet()
    rows = workitems.worktree_states(".")
    if args.action == "clean":
        return _clean(args, cfg, rows)
    if args.json:
        print(json.dumps({"worktrees": rows, "cleanable": [r["path"] for r in workitems.cleanable(rows, os.getcwd())]}, indent=2))
        return 0
    if not rows:
        print("No worktrees.")
        return 0
    for r in rows:
        what = r["item"] or r["branch"] or f"detached at {str(r['head'])[:12]}"
        extra = " (main)" if r["main"] else ""
        free = ", explore: never merges" if workitems.merges_nothing(r["branch"] or "") else ""
        print(f"{r['state']:17} {what:20} {r['path']}{extra}{free}  [AIDD_WORKTREE={r['slug']}]")
    gone = workitems.cleanable(rows, os.getcwd())
    if gone:
        print(f"\n{len(gone)} can go (missing, or merged with nothing uncommitted). Next: the person runs `aidd worktrees clean`.")
    return 0


def base_teardown() -> list[str] | None:
    """`project.dev_services.teardown` as the base branch's config holds it: the working tree's copy is an agent's to
    write, and the person who cleans runs it. None when the base has none, or its config does not load."""
    try:
        base = git.default_base(".")
    except git.GitError:
        return None
    text = git.show(base, config.CONFIG_PATH)
    if text is None:
        return None

    def offline(url: str) -> bytes:
        raise config.ConfigError(f"not fetched: {url}")

    try:
        cfg = config.load_text(text, read=lambda p: git.show(base, p), fetch=offline)
    except Exception:  # noqa: BLE001  # an unreadable base config runs nothing
        return None
    teardown = (cfg.get("project", "dev_services") or {}).get("teardown")
    return teardown if isinstance(teardown, list) and teardown and all(isinstance(a, str) for a in teardown) else None


def run_teardown(command: list[str], slug: str) -> bool:
    """Run one worktree's teardown without the person's credentials and for at most TEARDOWN_SECONDS: whether it ran
    and exited 0."""
    env = processes.scrub_credentials({**os.environ, "AIDD_WORKTREE": slug})
    try:
        code, _, _ = processes.run_bounded(command, timeout_seconds=TEARDOWN_SECONDS, cwd=".", env=env, capture=False)
    except OSError:
        return False
    return code == 0


def _clean(args, cfg, rows: list[dict]) -> int:
    gone = workitems.cleanable(rows, os.getcwd())
    if not gone:
        print("Nothing to clean: no worktree is missing, or merged with nothing uncommitted.")
        return 0
    for r in gone:
        print(f"would remove {r['path']} ({r['state']}{', ' + r['branch'] if r['branch'] else ''})" if args.dry_run else f"removing {r['path']} ({r['state']})")
    print(SESSIONS_NOTE)
    if args.dry_run:
        print("Nothing was removed (--dry-run). Branches are never deleted.")
        return 0
    try:
        platforms.require_person("Removing these worktrees", command="aidd worktrees clean", question=f"Remove {len(gone)} worktree(s)? Their branches stay.")
    except platforms.NotAPerson as exc:
        print(f"Not removed: {exc}", file=sys.stderr)
        return 1
    teardown = base_teardown()
    failed = 0
    for r in gone:
        if teardown and r["state"] != "missing" and not run_teardown(teardown, r["slug"]):
            print(f"warning: the teardown for {r['path']} failed or ran past {TEARDOWN_SECONDS}s", file=sys.stderr)
        if r["state"] == "missing":
            continue
        # Never --force: git refuses a worktree with changes, the last check that nothing is lost.
        if not git.ok(["worktree", "remove", r["path"]], "."):
            print(f"warning: git kept {r['path']}: it holds changes or is locked", file=sys.stderr)
            failed += 1
    git.run(["worktree", "prune"], ".", check=False)
    print(f"Removed {len(gone) - failed} worktree(s); their branches stay.")
    return 1 if failed else 0
