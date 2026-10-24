"""The other branches with open work, and the Specs on them that overlap this branch's: the same code in two Task
scopes, or one doc two Specs freeze. `aidd list` reads every branch's Specs from `branches`; the forecast reports
`overlaps`, so two changes to the same code learn about each other before the merge does."""

from __future__ import annotations

from pathlib import Path

from aidd import workitems
from aidd.kernel import documents, git, globs
from aidd.tracking.step import new_step

MAX_BRANCHES = 100


def branches(root: Path, base: str, *, include_here: bool) -> tuple[list[tuple[str, str]], int]:
    """The other local and remote-tracking branches with work the base lacks, as (name, tip), at most MAX_BRANCHES (the
    base, and this branch unless `include_here`, are left out before the cap), and how many there were. A branch whose
    tip another listed tip, or this branch, already holds adds no Spec of its own: its copies are older ones of those."""
    cwd = str(root)
    here = git.run(["rev-parse", "--abbrev-ref", "HEAD"], cwd, check=False).strip()
    head = git.run(["rev-parse", "-q", "--verify", "HEAD"], cwd, check=False).strip()
    listed = git.run(["for-each-ref", f"--no-merged={base}", "--format=%(objectname) %(refname:short)", "refs/heads", "refs/remotes"], cwd, check=False)
    refs = [(name, sha) for sha, _, name in (line.partition(" ") for line in listed.splitlines()) if name]
    base_names = {base, base.split("/", 1)[-1]}
    mine = () if include_here else (here, f"origin/{here}")
    others = [(r, s) for r, s in refs if not (r in base_names or r.endswith("/HEAD") or r in mine or r == "origin")]
    if include_here:  # this branch first: its copy wins over another branch's
        others.sort(key=lambda rs: rs[0] != here)
    own = workitems.independent_tips(cwd, [s for _, s in others] + ([head] if head and not include_here else []))
    kept: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r, s in others:
        if s in seen:
            continue  # another name for a tip already kept
        if (include_here and r == here) or (s in own and s != head):
            kept.append((r, s))
            seen.add(s)
    return kept[:MAX_BRANCHES], len(kept)


def capped_step(count: int) -> dict:
    what = f"only the first {MAX_BRANCHES} of {count} other branches were checked for overlapping Specs"
    return new_step(
        what, workitems.AUTHOR, "delete merged branches (`git branch --merged`, `git fetch --prune`) so every open one is checked", code="overlap.capped"
    )


def _scopes(data: dict) -> list[str]:
    return [g for t in data.get("tasks", []) or [] if isinstance(t, dict) for g in t.get("scope", []) or []]


def overlaps(root: Path, specs_dir: str, mine: list[tuple[str, dict]]) -> list[dict]:
    """Locks, found: another branch's Spec whose Task scope overlaps one of this branch's, or that freezes a doc one of
    this branch's also freezes (two approved versions of one document). With several people, each with their own
    agents, this is how two changes to the same code learn about each other before the merge does."""
    ours = [(data, _scopes(data)) for _, data in mine if _scopes(data) or workitems.frozen_docs(data)]
    if not ours:
        return []
    cwd = str(root)
    try:
        base = git.default_base(cwd)
    except git.GitError:
        return []
    head = git.rev_parse("HEAD", cwd)
    refs, total = branches(root, base, include_here=False)
    steps = [capped_step(total)] if total > MAX_BRANCHES else []
    seen: set[str] = set()
    for ref, sha in refs:
        if sha == head:
            continue
        fork = git.run(["merge-base", base, sha], cwd, check=False).strip()
        if not fork:
            continue
        changed = git.run(["diff", "--name-only", "-z", f"{fork}..{ref}", "--", specs_dir], cwd, check=False).split("\0")
        for rel in [p for p in changed if p]:
            text = git.show(ref, rel, cwd)
            try:
                other, _ = documents.split_front_matter(text or "", rel)
            except documents.DocumentError:
                continue
            oid = str(other.get("id"))
            if other.get("kind") != "spec" or oid in seen or workitems.spec_status(other) in workitems.UNBLOCKS:
                continue
            theirs, their_docs = _scopes(other), workitems.frozen_docs(other)
            for data, scopes in ours:
                if oid == str(data.get("id")):
                    continue
                docs = [d for d in workitems.frozen_docs(data) if any(globs.overlap(d, o) for o in their_docs)]
                if docs or any(globs.overlap(a, b) for a in scopes for b in theirs):
                    seen.add(oid)
                    who = git.run(["log", "-1", "--format=%an", ref], cwd, check=False).strip() or "someone"
                    what = f"{data.get('id')} overlaps {oid} on {ref} ({who}): the same code, changed twice"
                    if docs:
                        what = f"{data.get('id')} overlaps {oid} on {ref} ({who}): both freeze {', '.join(docs)}, two approved versions of one doc"
                    how = f"agree with {who} who goes first; the later change waits with `blockers: {oid}`, or `relations: [{{type: blocked_by, id: {oid}}}]`"
                    steps.append(new_step(what, workitems.AUTHOR, how, rel, code="overlap"))
                    break
    return steps
