"""Where aidd writes, by one rule (docs/ARCHITECTURE.md, "Where aidd writes").

- A file directly in `.aidd/` is committed: the config, and what init and the approvers keep beside it. `.aidd/**` is
  a protected path, so only a person changes it.
- A folder in `.aidd/` is aidd's own output for this worktree, which git ignores (OUTPUT_IGNORE): the evidence, with
  the preview captures beside it, and the decision pages. Being under `.aidd/`, an agent's edit tools cannot write
  them either: aidd's commands do (`aidd test`, `aidd record artifacts`, the `--html` pages).
- What every worktree shares lives in the git directory (`state_dir`): the autopilot lease and journal, the session
  snapshots, the watched state, and the guard's log. It is never in a working tree, so it has nothing to commit.
"""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import git

EVIDENCE_DIR = ".aidd/evidence"
VIEWS_DIR = ".aidd/views"
# What the verifier captured for people, beside the evidence: artifacts.json names each file relative to the evidence.
PREVIEW_DIR = f"{EVIDENCE_DIR}/preview"
# The one .gitignore line `aidd init` writes: every folder in .aidd/, never a file there.
OUTPUT_IGNORE = "/.aidd/*/"
# The folder in the git common directory, and the guard's log in it.
STATE_DIR = "aidd"
GUARD_LOG_FILE = "guard.jsonl"
# The folder in it that keeps each worktree's watched state, what the always-on rules stood on at a person's last
# decision (guard/outside_changes.py).
WATCHED_STATE_DIR = "watched-state"


def state_dir(root: Path | str) -> Path:
    """The folder in the git common directory that every worktree of the repository shares; ValueError outside git."""
    cwd = str(root)
    raw = git.run(["rev-parse", "--git-common-dir"], cwd, check=False).strip()
    if not raw:
        raise ValueError("not a git repository: aidd keeps the state every worktree shares in the git directory")
    common = Path(raw)
    if not common.is_absolute():
        common = Path(cwd) / common
    return common.resolve() / STATE_DIR


def guard_log(root: Path | str) -> Path:
    """The guard's denial log, which `aidd hook pre-tool` appends to and `aidd metrics --guard` counts."""
    return state_dir(root) / GUARD_LOG_FILE
