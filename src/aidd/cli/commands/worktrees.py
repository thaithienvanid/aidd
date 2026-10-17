"""`aidd worktrees`: every worktree of the repository, what it holds, and its state (workitems/worktree_states.py);
`aidd worktrees clean`: removes the ones that are missing or merged, after a person's yes."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from aidd import platforms, workitems
from aidd.cli import arguments
from aidd.kernel import git


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
        free = ", explore: free edits, never merges" if workitems.is_explore(r["branch"] or "") else ""
        print(f"{r['state']:17} {what:20} {r['path']}{extra}{free}  [AIDD_WORKTREE={r['slug']}]")
    gone = workitems.cleanable(rows, os.getcwd())
    if gone:
        print(f"\n{len(gone)} can go (missing, or merged with nothing uncommitted). Next: the person runs `aidd worktrees clean`.")
    return 0


def _clean(args, cfg, rows: list[dict]) -> int:
    gone = workitems.cleanable(rows, os.getcwd())
    if not gone:
        print("Nothing to clean: no worktree is missing, or merged with nothing uncommitted.")
        return 0
    for r in gone:
        print(f"would remove {r['path']} ({r['state']}{', ' + r['branch'] if r['branch'] else ''})" if args.dry_run else f"removing {r['path']} ({r['state']})")
    if args.dry_run:
        print("Nothing was removed (--dry-run). Branches are never deleted.")
        return 0
    try:
        platforms.require_person("Removing these worktrees", command="aidd worktrees clean", question=f"Remove {len(gone)} worktree(s)? Their branches stay.")
    except platforms.NotAPerson as exc:
        print(f"Not removed: {exc}", file=sys.stderr)
        return 1
    teardown = ((cfg.get("project", "dev_services") if cfg else None) or {}).get("teardown")
    failed = 0
    for r in gone:
        if teardown and r["state"] != "missing":
            subprocess.run(teardown, cwd=".", env={**os.environ, "AIDD_WORKTREE": r["slug"]}, check=False)
        if r["state"] == "missing":
            continue
        # Never --force: git refuses a worktree with changes, the last check that nothing is lost.
        if not git.ok(["worktree", "remove", r["path"]], "."):
            print(f"warning: git kept {r['path']}: it holds changes or is locked", file=sys.stderr)
            failed += 1
    git.run(["worktree", "prune"], ".", check=False)
    print(f"Removed {len(gone) - failed} worktree(s); their branches stay.")
    return 1 if failed else 0
