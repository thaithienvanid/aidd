"""A Spec stays frozen as its approval froze it until `aidd revise` reopens it.

A change to the Spec, or to a file or section it freezes, changes its hash, so the approval of the old hash stops
holding. Read alone, the Spec would then be a draft, and its tests would open to edits before the person approves it
again. While a counted approval of an earlier version stands on this branch, the Spec stays frozen, and what that
approval froze stays frozen with it, whatever the working tree now says about its route, test mode, id, or files.
Only a committed `revisions` entry that names the approved hash, as `aidd revise` writes it, reopens the Spec.

An approval stands on this branch when its commit is in the branch's history, when the branch had the approved text
at one of its commits (a rebase), or when git's reflog says the branch once pointed at it: a squash, an amend, or a
rename keeps it. It reads the decision records on this machine; where approvals live only on a platform, the stored
status answers, as `Observer.holds` says.
"""

from __future__ import annotations

from aidd.kernel import documents, git
from aidd.workitems.derived_status import Observer

MAX_BRANCH_COMMITS = 200  # the commits since the fork a rebased approval is looked for in


def standing_approval(obs: Observer, rel: str, data: dict, handled: set[str] | None = None) -> tuple[str, str, dict] | None:
    """(commit, hash, front matter) of the approval of an earlier version that still freezes the Spec at `rel`, while
    no approval of it holds: the newest counted one of its id on this branch, until a committed `revisions` entry names
    that hash. With `handled`, the ids the active Specs claim, it falls back to another standing approval of this branch
    whose lineage holds `rel` (`standing_approvals`), the one rule the guard's denial names too, so `aidd revise` writes
    the revision where it reopens what the guard holds."""
    committed = _front(git.show(obs.head, rel, obs.cwd) if obs.head else None, rel)
    revisions = [r.get("was") for r in _list((committed or {}).get("revisions")) if isinstance(r, dict)]
    for sid in dict.fromkeys(str(d.get("id")) for d in (data, committed) if d and d.get("id")):
        if found := _approval(obs, sid):
            return None if found[1] in revisions else found
    for one in standing_approvals(obs, handled) if handled is not None else []:
        if rel in one[4]:
            return one[0], one[1], one[2]
    return None


def standing_approvals(obs: Observer, handled: set[str]) -> list[tuple[str, str, dict, str, list[str]]]:
    """(commit, hash, front matter, path then, lineage) of every approval made on this branch of an id not in
    `handled`, the newest per id, that no Spec in its lineage (`_lineage`) reopened. Each freezes what it froze,
    whatever file claims what now: a changed id, a moved, removed, or decoy Spec never sheds it. Candidates: those on
    the branch (one `git rev-list`), and those off it whose id the branch's own diff of the specs folder names (a
    rebase, an empty or a merge commit too); every one when git cannot answer."""
    candidates = [(s, sha) for s, sha in obs.approvals() if s not in handled]
    if not candidates or not obs.head:
        return []
    since = f"{obs.base_sha}..{obs.head}" if obs.base_sha else str(obs.head)
    specs = str(obs.cfg.specs_dir if obs.cfg else "specs")
    try:
        on_branch: set[str] | None = set(git.run(["rev-list", since], obs.cwd).split())
        named: str | None = git.run(["log", "-p", "--no-color", "--no-ext-diff", since, "--", specs], obs.cwd)
    except git.GitError:
        on_branch, named = None, None
    held = _branch_reflog(obs)
    on = {s for s, sha in candidates if (on_branch is not None and sha in on_branch) or sha in held}
    ids = [s for s in dict.fromkeys(s for s, _ in candidates) if on_branch is None or named is None or s in on or s in named]
    found: list[tuple[str, str, dict, str, list[str]]] = []
    for sid in ids:
        if one := _approval(obs, sid):
            lineage = _lineage(obs, sid, one[0])
            if not _reopened(obs, one[1], lineage, one[0]):
                found.append((*one, obs.spec_path_at(sid, one[0]) or "", lineage))
    return found


def _lineage(obs: Observer, sid: str, sha: str) -> list[str]:
    """The files at HEAD that are the approved Spec now, the likeliest first: the one its file at the approved commit
    was renamed to (git's rename detection), that file itself, and the one that claims its id. A revision elsewhere
    never reopens it, and `aidd revise` reopens it only through one of these."""
    then = obs.spec_path_at(sid, sha)
    paths: list[str] = []
    if then:
        moved = git.run(
            ["diff", "--find-renames", "--name-status", "-z", sha, str(obs.head), "--", str(obs.cfg.specs_dir if obs.cfg else "specs")],
            obs.cwd,
            check=False,
            raw=True,
        )
        fields = [f for f in moved.split("\0") if f]
        paths += [fields[i + 2] for i in range(len(fields) - 2) if fields[i].startswith("R") and fields[i + 1] == then]
        paths.append(then)
    claimant = obs.spec_path_at(sid, str(obs.head))
    return list(dict.fromkeys([*paths, *([claimant] if claimant else [])]))


def _reopened(obs: Observer, h: str, paths: list[str], approved: str) -> bool:
    """Whether one of the Specs in `paths` (`_lineage`) holds a `revisions` entry naming hash `h`, as `aidd revise`
    writes it, as committed at HEAD. Only when none of them is at HEAD any more (a Spec restored, revised, and removed
    again), at a commit after the approval at `approved` that added it there (`git log -G`). A revision in any other
    file never counts, and one removed from a Spec still at HEAD no longer does."""
    heads = {p: git.show(obs.head, p, obs.cwd) if obs.head else None for p in dict.fromkeys(paths)}
    for path, text in heads.items():
        front = _front(text, path) or {}
        if any(isinstance(r, dict) and r.get("was") == h for r in _list(front.get("revisions"))):
            return True
    if not paths or not obs.head or any(text is not None for text in heads.values()):
        return False
    for sha in git.run(["log", "--format=%H", f"-G{h}", f"{approved}..{obs.head}", "--", *heads], obs.cwd, check=False).split():
        for path in dict.fromkeys(paths):
            front = _front(git.show(sha, path, obs.cwd), path) or {}
            if any(isinstance(r, dict) and r.get("was") == h for r in _list(front.get("revisions"))):
                return True
    return False


def approved_text(obs: Observer, rel: str, data: dict) -> dict | None:
    """The front matter of what the standing approval of the Spec at `rel` froze, or None when nothing freezes it: the
    committed Spec (the working tree's when HEAD has none) while its approval holds, else `standing_approval`'s text."""
    if obs.holds(rel, data):
        committed = git.show(obs.head, rel, obs.cwd) if obs.head else None
        if obs.head and committed is not None and obs.knows_approvals() and not obs.approved(str(data.get("id")), obs.hash_at(obs.head, committed)):
            return data  # the working tree's text is the one a person approved, not HEAD's
        return _front(committed, rel) or data
    found = standing_approval(obs, rel, data)
    return found[2] if found else None


def _approval(obs: Observer, sid: str) -> tuple[str, str, dict] | None:
    """(commit, hash, front matter) of the newest counted approval of `sid` on this branch: none once the base branch
    holds an approved text of it (a landed Spec, which is never reopened), and one HEAD does not hold only when the
    branch had the approved text (a rebase), or once pointed at it (`_branch_reflog`: a squash or an amend) while a file
    in the Spec's lineage is still at HEAD. The Spec is found by its id at that commit, so a rename keeps the approval."""
    if not obs.head:
        return None
    for spec_id, sha in obs.approvals():
        if spec_id != sid or sha == obs.base_sha or (obs.base_sha and git.ok(["merge-base", "--is-ancestor", sha, obs.base_sha], obs.cwd)):
            continue
        path = obs.spec_path_at(sid, sha)
        text = git.show(sha, path, obs.cwd) if path else None
        then = _front(text, path or "")
        h = obs.hash_at(sha, text) if text is not None and then and str(then.get("id")) == sid else None
        here = h and (git.ok(["merge-base", "--is-ancestor", sha, obs.head], obs.cwd) or h in _branch_hashes(obs, sid) or _left_by_a_rewrite(obs, sha))
        if h and h == _hash_on_base(obs, sid):  # the text the base branch already holds: landed, by a squash too
            if here:
                return None  # this branch landed it, so no older approval of it freezes it again
            continue
        if here:
            return sha, h, then  # type: ignore[return-value]
    return None


def _hash_on_base(obs: Observer, sid: str) -> str | None:
    """Spec `sid`'s hash at the base branch's tip, or None when the base holds no such Spec."""
    path = obs.spec_path_at(sid, obs.base_sha) if obs.base_sha else None
    text = git.show(obs.base_sha, path, obs.cwd) if path and obs.base_sha else None
    return obs.hash_at(obs.base_sha, text) if text is not None and obs.base_sha else None


def _left_by_a_rewrite(obs: Observer, sha: str) -> bool:
    """Whether a squash, an amend, or `reset --soft` took the approved commit out of this branch's history: the branch's
    reflog holds it, and the branch carries work of its own. Removing the Spec never sheds it, as removing it in a
    commit doesn't (`frozen_files`). A branch whose head is on the base branch (work abandoned by a reset to the base)
    carries nothing to freeze."""
    if not obs.head or sha not in _branch_reflog(obs):
        return False
    return not (obs.base_sha and git.ok(["merge-base", "--is-ancestor", str(obs.head), obs.base_sha], obs.cwd))


def _branch_reflog(obs: Observer) -> set[str]:
    """The commits the checked-out branch has pointed at, as git's reflog of it records them: a squash, an amend, or
    `reset --soft` leaves the approved commit there, and a rename moves the reflog with the branch. Every entry, so no
    run of amends pushes an approval out of reach. Only this branch's own, never HEAD's, which also holds every other
    branch checked out here. Empty when detached."""
    branch = git.run(["symbolic-ref", "-q", "HEAD"], obs.cwd, check=False).strip()
    if not branch.startswith("refs/heads/"):
        return set()
    key = (str(obs.cwd), branch, obs.head)
    if key not in _REFLOGS:
        _REFLOGS.clear()
        _REFLOGS[key] = frozenset(git.run(["reflog", "show", "--format=%H", branch], obs.cwd, check=False).split())
    return set(_REFLOGS[key])


# The last reflog read, by folder, branch, and head: one guard call asks for it once per approval.
_REFLOGS: dict[tuple[str, str, str | None], frozenset[str]] = {}


def _branch_hashes(obs: Observer, sid: str) -> set[str]:
    """The hashes Spec `sid` had at each commit of this branch since the fork (at most MAX_BRANCH_COMMITS)."""
    since = f"{obs.base_sha}..{obs.head}" if obs.base_sha else str(obs.head)
    commits = git.run(["log", f"-{MAX_BRANCH_COMMITS}", "--format=%H", since], obs.cwd, check=False).split()
    found = set()
    for sha in commits:
        path = obs.spec_path_at(sid, sha)
        text = git.show(sha, path, obs.cwd) if path else None
        if text is not None and (h := obs.hash_at(sha, text)):
            found.add(h)
    return found


def _front(text: str | None, rel: str) -> dict | None:
    try:
        return documents.split_front_matter(text, rel)[0] if text is not None else None
    except documents.DocumentError:
        return None


def _list(value: object) -> list:
    return value if isinstance(value, list) else []
