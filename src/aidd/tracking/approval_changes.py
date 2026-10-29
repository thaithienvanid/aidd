"""What changed in a Spec and its frozen files since the person last approved it, which a second approval shows first."""

from __future__ import annotations

from pathlib import Path

from aidd import gate, workitems
from aidd.kernel import documents, git, globs


def earlier_spec_approval(spec_id: str, spec_hash: str, spec_path: str) -> str | None:
    """The commit the newest recorded approval of this Spec names, when the Spec read otherwise there (local approvals);
    None when there is none, or it read the same."""
    try:
        _, comments, _ = workitems.load_local_approvals(".")
    except (git.GitError, OSError, ValueError):
        return None
    named = [m.group(2) for c in comments for m in gate.APPROVE_SPEC.finditer(c["body"]) if m.group(1) == spec_id]
    for sha in reversed(named):
        text = git.show(sha, spec_path)
        if text is None:
            continue
        try:
            same = workitems.spec_hash(text, git.ls_tree(sha), lambda p, at=sha: git.show(at, p)) == spec_hash
        except (git.GitError, documents.DocumentError):
            continue
        return None if same else sha
    return None


# At most this many changed lines go into a dialog; the rest are counted (the terminal and `aidd hash --html` show all).
CHANGED_LINES = 24


def tests_changed(spec_path: str, data: dict, since: dict | None, head: str) -> str:
    """The line a second Spec approval leads with when the tests changed since the last one, so a weaker test never
    hides in the diff: the Spec's own `tests:` block, a test file either Spec names, or a frozen manifest section (never
    the rest of the manifest, so a dependency bump stays quiet). '' on a first approval, or when only the rest of the
    Spec, its design, or its docs changed. Failing closed: an earlier Spec it cannot read counts as a changed tests block."""
    if not since:
        return ""
    earlier = since["commit"]
    try:
        before, _ = documents.split_front_matter(git.show(earlier, spec_path) or "", spec_path)
    except documents.DocumentError:
        before = {}
    names = ["the Spec's tests block"] if before.get("tests") != data.get("tests") else []
    entries = [e for s in (before, data) for e in [*(s.get("tests") or {}).get("files", []), *workitems.command_path_literals(s)]]
    whole = [e for e in entries if "#" not in e]
    frozen = list(dict.fromkeys([*workitems.frozen_files(before), *workitems.frozen_files(data)]))
    # Raw paths, NUL-separated and with no rename pairing, so a quoted or cleaned name can never miss a match.
    try:
        raw = git.run(["diff", "--name-only", "-z", "--no-renames", earlier, head, "--", *frozen], raw=True)
    except git.GitError:  # failing closed: a comparison git cannot make is a change
        raw, names = "", [*names, "the frozen tests (git could not compare them)"]
    for path in (p for p in raw.split("\0") if p and p != spec_path):
        keys = {e.partition("#")[2] for e in entries if "#" in e and e.partition("#")[0] == path}
        if globs.match_any(whole, path):
            names.append(path)
        elif keys:  # a frozen section, by the Spec's own key: only a change to it counts, read as the Spec hash reads it
            names += [f"{path}#{k}" for k in sorted(keys) if _section_at(f"{path}#{k}", earlier) != _section_at(f"{path}#{k}", head)]
    if not names:
        return ""
    shown = ", ".join(documents.one_line(n, 60) for n in names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
    return f"{len(names)} test change{'s' if len(names) > 1 else ''} since its last approval at {earlier[:12]}: {shown}. Read the diff before you approve."


def _section_at(entry: str, commit: str) -> str | None:
    """A frozen section's value at `commit` as the Spec hash holds it (section_digest); a commit git cannot read gives a
    value of its own, so it counts as changed."""
    try:
        return workitems.section_digest(entry, git.ls_tree(commit), lambda p: git.show(commit, p))
    except git.GitError:
        return f"unreadable:{commit}"


def changed_since(spec_path: str, data: dict, spec_hash: str, head: str) -> dict | None:
    """What changed in the Spec and its frozen files since the last approval of them as they read before: the commit it
    named, the files with their counts, and the first changed lines; None for a first approval."""
    earlier = earlier_spec_approval(str(data.get("id")), spec_hash, spec_path)
    if not earlier:
        return None
    frozen = [spec_path, *workitems.frozen_files(data)]
    stat = git.run(["diff", "--numstat", "--no-renames", earlier, head, "--", *frozen], check=False).splitlines()
    diff = git.run(["diff", "--no-color", "--no-ext-diff", "--no-renames", "-U0", earlier, head, "--", *frozen], check=False).splitlines()
    lines = [d for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---"))]
    return {
        "commit": earlier,
        "files": [{"path": documents.one_line(p, 160), "added": a, "removed": r} for a, r, p in (s.split("\t", 2) for s in stat if s.count("\t") >= 2)],
        "lines": [documents.one_line(line, 160) for line in lines[:CHANGED_LINES]],
        "more": max(0, len(lines) - CHANGED_LINES),
    }


def left_branch_changes(head: str, cfg) -> list[str]:
    """The lines a Merge approval leads with for each Spec approved on this branch whose file is no longer at `head`
    (revised and removed, or dropped): the files it froze that changed since that approval. With no Spec left, no
    second Spec approval would show them, so a test edited after such a revision never merges unseen. An approval
    counts as this branch's when HEAD holds its commit or the branch's reflog does, and never when the base holds it."""
    obs = workitems.Observer(Path("."), cfg)
    branch = git.run(["symbolic-ref", "-q", "HEAD"], check=False).strip()
    held = set(git.run(["reflog", "show", "--format=%H", branch], check=False).split()) if branch.startswith("refs/heads/") else set()
    lines: list[str] = []
    seen: set[str] = set()
    for sid, sha in obs.approvals():  # newest first: one line per Spec, from its newest approval here
        if sid in seen or (obs.base_sha and git.ok(["merge-base", "--is-ancestor", sha, obs.base_sha])):
            continue
        if not (git.ok(["merge-base", "--is-ancestor", sha, head]) or sha in held):
            continue
        seen.add(sid)
        path = obs.spec_path_at(sid, sha)
        if not path or obs.spec_path_at(sid, head):
            continue  # still on the branch: its own Spec approval shows what changed
        try:
            data = documents.split_front_matter(git.show(sha, path) or "", path)[0]
        except documents.DocumentError:
            data = {}
        frozen = [path, *workitems.frozen_files(data)]
        stat = git.run(["diff", "--numstat", "--no-renames", sha, head, "--", *frozen], check=False).splitlines()
        files = [(p, a, r) for a, r, p in (s.split("\t", 2) for s in stat if s.count("\t") >= 2) if p != path]
        if not files:
            continue
        shown = ", ".join(f"{documents.one_line(p, 80)} (+{a} -{r})" for p, a, r in files[:4]) + (f", and {len(files) - 4} more" if len(files) > 4 else "")
        lines.append(
            f"{sid} was approved on this branch at {sha[:12]}, then left it, so no Spec approval shows its tests again: "
            f"{len(files)} file{'s' if len(files) > 1 else ''} it froze changed since: {shown}. Read the diff before you approve."
        )
    return lines
