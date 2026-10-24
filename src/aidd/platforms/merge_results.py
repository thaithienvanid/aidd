"""The merged result a platform builds before it merges, as git computes it: the tree of an approved head merged onto a
commit, and the commit a GitLab merge-train car was built on. GitHub's merge queue and GitLab's merge train both
bind their commit to the approved head by its tree, so the gate and `aidd test` compute it the same way."""

from __future__ import annotations

import re

from aidd.kernel import git

COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
# Where the gate fetches the commit a merge queue built for an entry: GitHub's merge group, or GitLab's merge-train car.
# Before 1.0 the two had refs of their own (`refs/aidd/merge-group`, `refs/aidd/merge-train`); `aidd upgrade` removes them.
MERGE_QUEUE_REF = "refs/aidd/merge-queue"
# A car is built on the target branch or on a car ahead; past this many commits between them, no parent is tried.
MAX_TRAIN_CANDIDATES = 250


def merged_tree(cwd: str, parent: str, head: str) -> str | None:
    """The tree of `head` merged into `parent` (git merge-tree, 2.38 or later), or None when the merge conflicts."""
    p = git._git(["merge-tree", "--write-tree", "--no-messages", parent, head], cwd)
    out = p.stdout.decode("utf-8", errors="replace").split("\n", 1)[0].strip()
    if p.returncode == 0 and COMMIT_SHA.match(out):
        return out
    if p.returncode == 1:
        return None
    raise git.GitError(f"git merge-tree {parent[:12]} {head[:12]}: {p.stderr.decode('utf-8', errors='replace').strip()}")


def train_parent(cwd: str, sha: str, head: str, base_tip: str) -> tuple[str, bool]:
    """The commit a merge-train car `sha` was built on, and whether that is a car ahead (stacked) rather than the
    target branch.

    GitLab builds a car on the target branch or on the car ahead, so that commit is on the car's first-parent chain:
    in a merge-commit train it is the car's first parent. The parent is the newest commit on that chain, from the
    car's first parent back to the merge base of the target and the car, whose merge with `head` gives exactly the
    car's tree. The merge request's own commits are never on that chain, and a rebased copy of one (a fast-forward
    train) is skipped. Newest first, a car names the same parent before and after the car ahead merges. When none
    matches, it is the merge base, and the gate's tree check then fails. The aidd-tests job and the gate both call
    this, so the evidence's base and the gate's expectation are computed the same way."""
    base = git.merge_base(base_tip, sha, cwd)
    tree = git.run(["rev-parse", "--verify", f"{sha}^{{tree}}"], cwd).strip()
    own = _authored(cwd, f"{base}..{head}")
    chain = _authored(cwd, f"{base}..{sha}", first_parent=True)  # newest first, the car itself first
    copies = set(own.values())
    candidates = [c for c, key in chain.items() if c != sha and c not in own and key not in copies] + [base]
    for candidate in candidates[:MAX_TRAIN_CANDIDATES]:
        if merged_tree(cwd, candidate, head) == tree:
            return candidate, candidate != base
    return base, False


def _authored(cwd: str, span: str, *, first_parent: bool = False) -> dict[str, str]:
    """Each commit of `span` and who wrote it when, with its subject: a rebase keeps all three, so a rebased copy of a
    merge request's commit carries the same key."""
    args = ["log", "--first-parent"] if first_parent else ["log"]
    out = git.run([*args, "--format=%H%x00%an <%ae> %at%x00%s", span], cwd)
    return {sha: key for line in out.splitlines() if line for sha, _, key in [line.partition("\0")]}
