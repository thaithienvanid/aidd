"""What git says about a goal branch (`goal/<name>`), the team's integration branch: which Specs it has integrated,
how old it is, and how far it is behind the default branch. Read from git each time, never from a record that drifts.

`aidd integrate` lands one Spec's branch in its goal as a merge commit with an `Aidd-Integrate: <ID>` trailer, so the
goal's own history says which Specs it holds. The trailer is a fact for `aidd list`, never an approval: at release the
goal gate proves each Spec again.
"""

from __future__ import annotations

import datetime as dt
import re

from aidd import config
from aidd.kernel import git
from aidd.workitems.small_goals import GOAL_PREFIX

INTEGRATE_TRAILER = "Aidd-Integrate"
UNDO_TRAILER = "Aidd-Undo"
# A goal stays short: `aidd list` and `aidd doctor` warn past this many days (a week) while limits.max_goal_age_days is unset.
MAX_GOAL_DAYS = 7
_TRAILER = re.compile(rf"^({INTEGRATE_TRAILER}|{UNDO_TRAILER}):[ \t]*(\S+)[ \t]*$", re.M)


def goal_branches(cwd: str = ".") -> list[str]:
    """The local goal branches, sorted."""
    out = git.run(["for-each-ref", "--format=%(refname:short)", f"refs/heads/{GOAL_PREFIX}"], cwd, check=False)
    return sorted(b for b in out.split() if b.startswith(GOAL_PREFIX))


def _default_tip(cwd: str) -> str | None:
    try:
        return git.rev_parse(git.default_base(cwd), cwd)
    except git.GitError:
        return None


def integrations(cwd: str, goal: str) -> dict[str, tuple[str, str]]:
    """{Spec id: (the commit on the goal that integrated it, the head it integrated)} for each Spec `aidd integrate`
    landed in `goal` since it left the default branch and `aidd integrate --undo` has not taken out since: the
    commits on the goal's first-parent line whose message carries a trailer, the newest one for each Spec deciding."""
    base = _default_tip(cwd)
    span = f"{base}..refs/heads/{goal}" if base else f"refs/heads/{goal}"
    out = git.run(["log", "--first-parent", "--format=%H%x00%P%x00%B%x1e", span], cwd, check=False)
    seen: dict[str, tuple[str, str] | None] = {}
    for record in out.split("\x1e"):
        parts = record.strip("\n").split("\x00")
        if len(parts) < 3:
            continue
        parents = parts[1].split()
        # Trailers sit in the message's last paragraph only, as git reads them: a subject never forges one.
        paragraphs = [p for p in parts[2].strip().split("\n\n") if p.strip()]
        trailers = paragraphs[-1] if len(paragraphs) > 1 else ""
        for which, sid in _TRAILER.findall(trailers):
            if sid in seen:
                continue
            seen[sid] = (parts[0], parents[1]) if which == INTEGRATE_TRAILER and len(parents) > 1 else None
    return {sid: v for sid, v in seen.items() if v is not None}


def integrated(cwd: str, goal: str) -> dict[str, str]:
    """{Spec id: the head integrated} for each Spec the goal holds now (integrations)."""
    return {sid: head for sid, (_, head) in integrations(cwd, goal).items()}


def goal_facts(cwd: str, goal: str, now: dt.datetime | None = None, *, head: str | None = None, base: str | None = None) -> dict:
    """{branch, head, age_days, behind}: the goal's tip, the days since its oldest commit the default branch lacks
    (0 when it has none yet), and how many default-branch commits it does not hold yet. `head` and `base` save a
    caller that has already read them a lookup each."""
    head = head or git.run(["rev-parse", "-q", "--verify", f"refs/heads/{goal}"], cwd, check=False).strip()
    base = base or _default_tip(cwd)
    facts: dict = {"branch": goal, "head": head, "age_days": 0, "behind": 0}
    if not head or not base:
        return facts
    first = git.run(["log", "--reverse", "--format=%cI", f"{base}..{head}"], cwd, check=False).split()
    if first:
        try:
            born = dt.datetime.fromisoformat(first[0])
            facts["age_days"] = max(0, ((now or dt.datetime.now(dt.UTC)) - born).days)
        except ValueError:
            pass
    behind = git.run(["rev-list", "--count", f"{head}..{base}"], cwd, check=False).strip()
    facts["behind"] = int(behind) if behind.isdigit() else 0
    return facts


def integrate_trailer(sid: str) -> str:
    """The trailer an integration's merge commit carries, which `integrated` reads back."""
    return f"{INTEGRATE_TRAILER}: {sid}"


def undo_trailer(sid: str) -> str:
    """The trailer of the commit that takes an integration out of its goal again."""
    return f"{UNDO_TRAILER}: {sid}"


def goal_limit(cfg: config.Config | None) -> int:
    """limits.max_goal_age_days, or MAX_GOAL_DAYS while unset; 0 turns the age warning off."""
    raw = cfg.limits.get("max_goal_age_days") if cfg is not None else None
    try:
        return MAX_GOAL_DAYS if raw is None else max(0, int(raw))
    except (TypeError, ValueError):
        return MAX_GOAL_DAYS


def goal_warnings(facts: dict, limit: int) -> list[str]:
    """What to do about a goal that lives too long or falls behind the default branch."""
    out = []
    g = facts["branch"]
    if limit and facts["age_days"] > limit:
        out.append(f"{g} is {facts['age_days']} days old, past limits.max_goal_age_days = {limit}: release what is integrated, or split the goal")
    if facts["behind"]:
        out.append(f"{g} is {facts['behind']} commit(s) behind the default branch: run `aidd sync` on it")
    return out


# Trunk-based development (DORA): three or fewer active branches, each living hours rather than days, merged to the
# default branch at least daily. Agents wait on a person's approvals, so the defaults allow two days a branch.
MAX_BRANCH_DAYS = 2
MAX_OPEN_BRANCHES = 3


def work_branches(cwd: str = ".", now: dt.datetime | None = None) -> list[dict]:
    """The local branches with work the default branch does not hold yet, goal branches aside (they have their own
    limit): {branch, head, age_days, behind}, oldest first. The age counts from the branch's oldest own commit. A branch
    whose work another such branch already holds (a Task branch merged into its Spec's) is that branch's work, not a
    branch of its own. Git is asked a fixed number of times, plus twice for each branch listed."""
    base = _default_tip(cwd)
    if base is None:
        return []
    listed = git.run(["for-each-ref", f"--no-merged={base}", "--format=%(objectname) %(refname:short)", "refs/heads/"], cwd, check=False)
    tips = [tuple(line.split(" ", 1)) for line in listed.splitlines() if " " in line]
    tips = [(sha, name) for sha, name in tips if not name.startswith(GOAL_PREFIX)]
    own = independent_tips(cwd, [sha for sha, _ in tips])
    out = []
    for sha, name in tips:
        if sha not in own:
            continue
        own.discard(sha)  # two names for one tip count once
        facts = goal_facts(cwd, name, now, head=sha, base=base)  # the same three facts a goal has
        out.append({k: facts[k] for k in ("branch", "head", "age_days", "behind")})
    return sorted(out, key=lambda b: -b["age_days"])


def unpublished_trunk(cwd: str = ".", now: dt.datetime | None = None) -> dict | None:
    """The local trunk's work its remote lacks, which only a person publishes: {branch, remote, commits, age_days}, the
    age counting from the oldest such commit; None when the remote holds it all, or holds no copy to compare with."""
    head = git.run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], cwd, check=False).strip()
    base = next((r for r in ([head] if head else []) + ["origin/main", "origin/master"] if git.ok(["rev-parse", "-q", "--verify", r], cwd)), "")
    remote, _, name = base.partition("/")
    if not name or not git.ok(["rev-parse", "-q", "--verify", f"refs/heads/{name}"], cwd):
        return None
    times = [int(t) for t in git.run(["log", "--format=%ct", f"{base}..refs/heads/{name}"], cwd, check=False).split() if t.isdigit()]
    if not times:
        return None
    now = now or dt.datetime.now(dt.UTC)
    return {"branch": name, "remote": remote, "commits": len(times), "age_days": max(0, int((now.timestamp() - min(times)) // 86400))}


def independent_tips(cwd: str, shas: list[str]) -> set[str]:
    """The commits among `shas` that no other one of them holds (`git merge-base --independent`), in one call."""
    unique = list(dict.fromkeys(shas))
    if len(unique) < 2:
        return set(unique)
    out = git.run(["merge-base", "--independent", *unique], cwd, check=False).split()
    return set(out) if out else set(unique)


def _limit(cfg: config.Config | None, key: str, default: int) -> int:
    raw = cfg.limits.get(key) if cfg is not None else None
    try:
        return default if raw is None else max(0, int(raw))
    except (TypeError, ValueError):
        return default


def flow_warnings(branches: list[dict], cfg: config.Config | None, unpublished: dict | None = None) -> list[str]:
    """What keeps the work trunk-based: too many open branches (limits.max_open_branches), each branch older than
    limits.max_branch_age_days, and a local trunk whose oldest unpublished commit is older than that too
    (`unpublished_trunk`). 0 turns either off."""
    out = []
    most, days = _limit(cfg, "max_open_branches", MAX_OPEN_BRANCHES), _limit(cfg, "max_branch_age_days", MAX_BRANCH_DAYS)
    if most and len(branches) > most:
        out.append(
            f"{len(branches)} branches hold work the default branch lacks, past limits.max_open_branches = {most}: land or drop the oldest before starting more"
        )
    for b in branches:
        if days and b["age_days"] > days:
            out.append(
                f"{b['branch']} is {b['age_days']} days old, past limits.max_branch_age_days = {days}: land it today (behind a flag if unfinished), or split it"
            )
    if unpublished and days and unpublished["age_days"] > days:
        out.append(
            f"{unpublished['branch']} holds {unpublished['commits']} commit(s) {unpublished['remote']} lacks, the oldest "
            f"{unpublished['age_days']} days old, past limits.max_branch_age_days = {days}: the person publishes them (they type "
            f"`publish` on {unpublished['branch']}, or run `aidd publish`)"
        )
    return out
