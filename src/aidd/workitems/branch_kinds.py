"""Branches and what they are for. The loop is always on; how the guard holds a worktree follows its branch.

- A `explore/<topic>` branch is free work: a spike, a prototype, or a person's own experiment. The guard lets every
  edit through there, with no Spec or scope check, and nothing merges from it as it is: the gate fails a change whose
  head branch is an explore branch (rule `explore`), and `aidd land` and `aidd integrate` refuse one. What it found
  reaches the default branch as a change of its own, through the loop. A branch named before 1.0's rename
  (`explore/<topic>`) is an ordinary branch now, with its edits checked, and still nothing merges from it as it is.
- A goal branch (`goal/<EPIC>`) is a small goal that is batched; work cut from it builds on it (builds_on, goal_of).
- `components.spec_steps: false` in the config switches the loop's Spec steps and edit checks off for a whole
  repository that adopts only part of aidd.

The guard keeps an agent from approving, merging, or moving a protected branch on every branch.
"""

from __future__ import annotations

import re

from aidd import config
from aidd.kernel import git
from aidd.workitems.small_goals import GOAL_PREFIX

# The trailer of the commit that opens a goal branch (`aidd goal open`).
GOAL_TRAILER = "Aidd-Goal"
# A step of the loop the person said to skip for this one change, in their words: `Aidd-Skipped: spec: just do it`.
# The agent writes it in the commit; the gate reports it and never decides on it (`skipped_steps`).
SKIPPED_TRAILER = "Aidd-Skipped"
EXPLORE_PREFIX = "explore/"


def current_branch(cwd: str = ".") -> str:
    """The branch checked out at `cwd`, or "" when HEAD is detached."""
    return git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()


def explore_note(branch: str) -> str:
    """What an explore branch is, said once where the person and the agent see it: the session start and `aidd list`."""
    return (
        f"{branch} is an explore branch: every edit is allowed here, with no Spec or scope check, and nothing merges from it as it "
        "is. Approving, landing, publishing, and merging stay the person's. To keep the work, rename the branch (`git branch -m <name>`): the "
        "gate then checks it as it checks any change"
    )


def spec_steps_off_note(cfg: config.Config | None, cwd: str = ".") -> str | None:
    """When the config switches the Spec steps off, what to tell the person, with the day they went off, so a switch
    nobody remembers is said at each session start, in `aidd list`, and in `aidd doctor`; None while they are on."""
    if cfg is None or config.component_on(cfg.raw, "spec_steps"):
        return None
    switch = r"^[^#]*spec_steps:[[:space:]]*false"  # a line that sets it, never the template's commented example
    committed = git.run(["show", f"HEAD:{config.CONFIG_PATH}"], cwd, check=False)
    day = git.run(["log", "-1", "--format=%cs", "-G", switch, "--", config.CONFIG_PATH], cwd, check=False).strip()
    on_head = any(not line.lstrip().startswith("#") and re.search(r"spec_steps:\s*false", line) for line in committed.splitlines())
    since = f"since {day}" if day and on_head else "in an edit not yet committed"
    return (
        f"the Spec steps are off here (`components.spec_steps: false` in .aidd/config.yaml, {since}): no Spec, lane, or approval step runs, "
        "and nothing needs it to, since advisory mode never stops work. To turn it back on, remove that line"
    )


def skipped_steps(commits: list) -> list[str]:
    """Each step a change's commits say the person skipped (SKIPPED_TRAILER), as a line for the gate's report: the
    agent's account of the person's words, shown as data, never a reason to pass."""
    out: list[str] = []
    for c in commits:
        if not isinstance(c, dict) or not isinstance(c.get("message"), str):
            continue
        for line in c["message"].splitlines():
            if line.startswith(f"{SKIPPED_TRAILER}: "):
                said = " ".join(line.split(": ", 1)[1].split())[:160]
                out.append(f"skipped by the person, as {str(c.get('sha', ''))[:12]} records it: {said!r}")
    return list(dict.fromkeys(out))


def is_explore(branch: str) -> bool:
    """Whether `branch` is an explore branch: free work that never merges as it is."""
    return branch.startswith(EXPLORE_PREFIX)


def explore_started(cfg: config.Config | None, cwd: str, branch: str) -> bool:
    """Whether `branch` is an explore branch the person started: the `explore/` prefix, and their recorded `explore branch
    <topic>` for exactly it (decision_records.explore_said_for). A branch that merely has the prefix frees no edit."""
    from aidd.workitems.decision_records import explore_said_for

    return is_explore(branch) and cfg is not None and explore_said_for(cfg, cwd, branch)


def unstarted_explore_note(branch: str) -> str:
    """What to tell the person on a `explore/` branch they did not start through aidd: an ordinary branch, its step."""
    topic = branch[len(EXPLORE_PREFIX) :]
    step = (
        f"To make it an explore branch, the person types `explore branch {topic}` at the prompt"
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,60}", topic)
        else "To start an explore branch, the person types `explore branch <topic>` at the prompt, with letters, digits, `.`, `_`, or `-`"
    )
    return (
        f"{branch} has the explore branch's prefix, but no record says the person started it, so its edits are checked as on any "
        f"branch, and nothing merges from it as it is. {step}"
    )


def merges_nothing(branch: str) -> bool:
    """Whether nothing merges from `branch` as it is: an explore branch."""
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
    active Spec lands in (`base`), when HEAD builds on that branch (builds_on); None otherwise. The agent writes the
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


def guard_mode(cfg: config.Config | None, cwd: str = ".") -> str:
    """How the guard holds an agent's edits in the worktree at `cwd` to the loop's rules (a Spec, its scope, each role's
    area): `free` where nothing holds them (`components.spec_steps` off, or an explore branch the person started), `advise` where the mode is
    advisory (an edit enforce mode would deny goes through, with a note to the agent), else `enforce`. The mode is the
    config's `mode`, else its profile's default (solo and team advise, org and audited enforce). The always-on rules hold in
    every one: no agent decides for a person (`guard.decision_change`, the guard's commands)."""
    if cfg is None:
        return "enforce"
    if not config.component_on(cfg.raw, "spec_steps") or explore_started(cfg, cwd, current_branch(cwd)):
        return "free"
    mode = config.effective_mode(cfg.get("mode"), None, input_trusted=False, fallback=config.profile_mode(cfg.profile))
    return "advise" if mode == "advisory" else "enforce"


def edits_held(cfg: config.Config | None, cwd: str = ".") -> bool:
    """Whether the guard holds edits in the worktree at `cwd` to the loop's rules: only in enforce mode (guard_mode)."""
    return guard_mode(cfg, cwd) == "enforce"
