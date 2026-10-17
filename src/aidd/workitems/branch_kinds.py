"""Branches and what they are for. The loop is always on; how the guard holds a worktree follows its branch.

- An `explore/<topic>` branch is free work: a spike, a prototype, or a person's own experiment. The guard lets every
  edit through there, with no Spec or scope check, and nothing merges from it as it is: the gate fails a change whose
  head branch is an explore branch (rule `explore`), and `aidd ship` and `aidd integrate` refuse one. What it found
  reaches the default branch as a change of its own, through the loop.
- A goal branch (`goal/<EPIC>`) is a small goal that ships batched; work cut from it builds on it (builds_on, goal_of).
- `components.loop: false` in the config switches the loop's edit checks off for a whole repository that adopts only
  part of aidd.

The guard keeps an agent from approving, merging, or moving a protected branch on every branch.
"""

from __future__ import annotations

from aidd import config
from aidd.kernel import git
from aidd.workitems.small_goals import GOAL_PREFIX

# The trailer of the commit that opens a goal branch (`aidd goal open`).
GOAL_TRAILER = "Aidd-Goal"
EXPLORE_PREFIX = "explore/"


def current_branch(cwd: str = ".") -> str:
    """The branch checked out at `cwd`, or "" when HEAD is detached."""
    return git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()


def explore_note(branch: str) -> str:
    """What an explore branch is, said once where the person and the agent see it: the session start and `aidd list`."""
    return (
        f"{branch} is an explore branch: every edit is allowed here, with no Spec or scope check, and nothing merges from it as it "
        "is. Approving, merging, and shipping stay the person's. To keep the work, rename the branch (`git branch -m <name>`): the "
        "gate then checks it as it checks any change"
    )


def is_explore(branch: str) -> bool:
    """Whether `branch` is an explore branch: free work that never merges as it is."""
    return branch.startswith(EXPLORE_PREFIX)


def builds_on(cwd: str, branch: str) -> bool:
    """Whether HEAD at `cwd` builds on the local branch `branch`: it holds a commit that branch holds and the default
    branch does not. An agent writes a Spec's `base`, never this: only work cut from the branch has it."""
    from aidd.workitems.authoring import BASE_PATTERN

    if not BASE_PATTERN.match(branch):
        return False
    try:
        shared = git.merge_base(f"refs/heads/{branch}", "HEAD", cwd)
        return bool(shared) and not git.ok(["merge-base", "--is-ancestor", shared, git.default_base(cwd)], cwd)
    except git.GitError:
        return False


def goal_of(cwd: str, cfg=None) -> str | None:
    """The goal the worktree at `cwd` works on: its own branch when it is a `goal/` branch, else the goal its one
    active Spec ships into (`base`), when HEAD builds on that branch (builds_on); None otherwise. The agent writes the
    `base`, so the claim counts only with the history to back it: work cut from the goal, which lands in it."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()
    if branch.startswith(GOAL_PREFIX):
        return branch
    if cfg is None:
        return None
    from aidd.workitems import branch_specs
    from aidd.workitems.authoring import BASE_PATTERN

    try:
        specs = branch_specs.active_specs(cwd, cfg)
    except Exception:  # an agent writes the Specs: one aidd cannot read names no goal
        return None
    # A plain branch name only: aidd names the goal in its messages and commands, so never a newline or anything else.
    bases = {b for _, d in specs if (b := str(d.get("base") or "")).startswith(GOAL_PREFIX) and BASE_PATTERN.match(b)}
    return bases.pop() if len(bases) == 1 and builds_on(cwd, next(iter(bases))) else None


def edits_held(cfg: config.Config | None, cwd: str = ".") -> bool:
    """Whether the guard holds edits in the worktree at `cwd` to the loop's rules (a Spec, its scope, each role's area):
    yes, unless `components.loop` is off in the config, or the worktree is on an explore branch."""
    if cfg is None:
        return True
    return config.component_on(cfg.raw, "loop") and not is_explore(current_branch(cwd))
